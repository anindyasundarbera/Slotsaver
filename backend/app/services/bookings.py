from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..errors import Conflict, NotFound, Validation
from ..models import (
    AttemptStatus,
    Booking,
    BookingStatus,
    Hold,
    HoldStatus,
    PaymentAttempt,
    ProcessedPaymentEvent,
    ProposalStatus,
    ReassignmentProposal,
    Service,
    Technician,
    User,
)
from ..timeutil import is_business_open
from . import audit, availability
from .payments import OrderView, PaymentProvider, PaymentError, ProviderUnavailable

log = logging.getLogger("slotsaver.bookings")

STATUS_LABELS = {
    BookingStatus.held.value: "Held",
    BookingStatus.awaiting_payment.value: "Awaiting payment",
    BookingStatus.confirmed.value: "Confirmed",
    BookingStatus.needs_reassignment.value: "Needs reassignment",
    BookingStatus.payment_exception.value: "Payment exception",
    BookingStatus.cancelled.value: "Cancelled",
    BookingStatus.expired.value: "Expired",
}

LABEL_TO_STATUS = {label.lower(): status for status, label in STATUS_LABELS.items()}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.held.value: {
        BookingStatus.awaiting_payment.value,
        BookingStatus.expired.value,
        BookingStatus.cancelled.value,
    },
    BookingStatus.awaiting_payment.value: {
        BookingStatus.confirmed.value,
        BookingStatus.cancelled.value,
        BookingStatus.expired.value,
        BookingStatus.payment_exception.value,
    },
    BookingStatus.confirmed.value: {
        BookingStatus.needs_reassignment.value,
        BookingStatus.cancelled.value,
    },
    BookingStatus.needs_reassignment.value: {
        BookingStatus.confirmed.value,
        BookingStatus.needs_reassignment.value,
        BookingStatus.cancelled.value,
    },
    BookingStatus.payment_exception.value: {
        BookingStatus.cancelled.value,
        BookingStatus.confirmed.value,
    },
    BookingStatus.cancelled.value: set(),
    BookingStatus.expired.value: set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(booking: Booking, target: str, *, reason: str = "") -> None:
    if booking.status == target:
        return
    if not can_transition(booking.status, target):
        raise Validation(f"Illegal booking transition {booking.status} -> {target}")
    booking.status = target
    booking.exception_reason = reason
    if target == BookingStatus.confirmed.value:
        booking.confirmed_at = utcnow()
    if target == BookingStatus.cancelled.value:
        booking.cancelled_at = utcnow()


def make_reference() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"SA-{code}"


def hold_ttl(settings: Settings) -> timedelta:
    return timedelta(minutes=settings.hold_ttl_minutes)


# ------------------------------------------------------------------ holds
def create_hold(
    db: Session,
    settings: Settings,
    *,
    customer: User,
    service_code: str,
    technician_id: str,
    start_utc: datetime,
    notes: str = "",
    correlation_id: str = "",
) -> tuple[Hold, Booking]:
    now = utcnow()
    availability.expire_stale_holds(db, now)

    service = db.execute(select(Service).where(Service.code == service_code)).scalar_one_or_none()
    if service is None:
        raise Validation("Unknown service.")
    technician = db.execute(select(Technician).where(Technician.id == technician_id)).scalar_one_or_none()
    if technician is None or not technician.active:
        raise Validation("Unknown technician.")
    if service.required_skill not in (technician.skills or []):
        raise Conflict("TECHNICIAN_NOT_QUALIFIED", "That technician is not qualified for this service.")

    if start_utc.tzinfo is None:
        raise Validation("start_utc must be timezone-aware.")
    start_utc = start_utc.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(minutes=service.duration_minutes)

    # Capacity is keyed on 30-minute cells. An unaligned start would write cells
    # that collide with nothing and are invisible to availability search, which
    # would defeat the uniqueness guarantee. Reject it here and again in
    # `slot_starts` as defence in depth.
    from ..timeutil import is_slot_aligned

    if not is_slot_aligned(start_utc):
        raise Validation("start_utc must align to a 30-minute boundary (HH:00 or HH:30).")

    if not is_business_open(start_utc, end_utc, settings.tz):
        raise Conflict("OUTSIDE_BUSINESS_HOURS", "That time is outside business hours.")

    hold = Hold(
        customer_id=customer.id,
        technician_id=technician.id,
        service_id=service.id,
        start_utc=start_utc,
        end_utc=end_utc,
        price_cents=service.price_cents,
        currency=service.currency,
        status=HoldStatus.active.value,
        created_at=now,
        expires_at=now + hold_ttl(settings),
    )
    db.add(hold)
    try:
        db.flush()
        availability.claim_cells(db, technician.id, start_utc, end_utc, "hold", hold.id)
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("SLOT_UNAVAILABLE", "That slot was just taken. Please choose another option.") from exc

    booking = Booking(
        reference=make_reference(),
        customer_id=customer.id,
        technician_id=technician.id,
        service_id=service.id,
        hold_id=hold.id,
        start_utc=start_utc,
        end_utc=end_utc,
        price_cents=service.price_cents,
        currency=service.currency,
        status=BookingStatus.held.value,
        notes=notes,
    )
    db.add(booking)
    db.flush()
    audit.record(
        db,
        action="hold.created",
        actor_id=customer.id,
        actor_role="customer",
        subject_type="hold",
        subject_id=hold.id,
        detail={
            "technician_id": technician.id,
            "service": service.code,
            "start_utc": start_utc.isoformat(),
            "price_cents": service.price_cents,
        },
        correlation_id=correlation_id,
    )
    return hold, booking


def release_hold(db: Session, hold: Hold, *, reason: str) -> None:
    if hold.status != HoldStatus.active.value:
        return
    hold.status = HoldStatus.released.value
    availability.release_cells(db, "hold", hold.id)
    booking = db.execute(select(Booking).where(Booking.hold_id == hold.id)).scalar_one_or_none()
    if booking is not None and booking.status in {
        BookingStatus.held.value,
        BookingStatus.awaiting_payment.value,
    }:
        transition(booking, BookingStatus.cancelled.value, reason=reason)
    db.flush()


def cancel_hold(db: Session, *, customer: User, hold_id: str, correlation_id: str = "") -> Booking:
    hold = db.execute(select(Hold).where(Hold.id == hold_id)).scalar_one_or_none()
    if hold is None or hold.customer_id != customer.id:
        raise NotFound("Hold")
    availability.expire_stale_holds(db, utcnow())
    if hold.status != HoldStatus.active.value:
        raise Conflict("HOLD_NOT_ACTIVE", "This hold is no longer active.")
    release_hold(db, hold, reason="Customer cancelled checkout")
    booking = db.execute(select(Booking).where(Booking.hold_id == hold.id)).scalar_one()
    audit.record(
        db,
        action="hold.cancelled",
        actor_id=customer.id,
        actor_role="customer",
        subject_type="hold",
        subject_id=hold.id,
        correlation_id=correlation_id,
    )
    return booking


# ------------------------------------------------------------------ payment
def _idempotency_key(booking: Booking, hold: Hold, attempt_no: int = 1) -> str:
    """Stable key for one logical *create* operation."""
    return f"slotsaver:{hold.id}:{booking.id}:{attempt_no}:create"


def _capture_key(attempt: PaymentAttempt) -> str:
    """Stable key for one logical *capture* operation.

    Create and capture are separate operations at PayPal and must not share an
    idempotency key: a replayed create key would return the order and silently
    skip the capture.
    """
    return f"{attempt.idempotency_key}:capture"


def start_checkout(
    db: Session,
    settings: Settings,
    provider: PaymentProvider,
    *,
    customer: User,
    hold_id: str,
    correlation_id: str = "",
) -> tuple[PaymentAttempt, Hold, Booking]:
    now = utcnow()
    hold = db.execute(select(Hold).where(Hold.id == hold_id)).scalar_one_or_none()
    if hold is None or hold.customer_id != customer.id:
        raise NotFound("Hold")
    booking = db.execute(select(Booking).where(Booking.hold_id == hold.id)).scalar_one_or_none()
    if booking is None:
        raise NotFound("Booking")
    if booking.customer_id != customer.id:
        raise NotFound("Booking")

    if hold.status == HoldStatus.consumed.value or booking.status == BookingStatus.confirmed.value:
        existing = db.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.booking_id == booking.id)
            .order_by(PaymentAttempt.created_at.desc())
        ).scalars().first()
        if existing is not None:
            return existing, hold, booking

    if hold.expires_at <= now:
        availability.expire_stale_holds(db, now)
        db.commit()
        raise Conflict("HOLD_EXPIRED", "This hold expired. Please pick a slot again.")
    if hold.status != HoldStatus.active.value:
        raise Conflict("HOLD_NOT_ACTIVE", "This hold is no longer active.")
    if booking.status not in {BookingStatus.held.value, BookingStatus.awaiting_payment.value}:
        raise Conflict("BOOKING_NOT_PAYABLE", f"Booking is {booking.status} and cannot be paid.")

    existing = db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.hold_id == hold.id,
            PaymentAttempt.status.in_(
                [
                    AttemptStatus.created.value,
                    AttemptStatus.approved.value,
                ]
            ),
        )
    ).scalars().first()
    if existing is not None:
        return existing, hold, booking

    # A closed attempt (failed/cancelled) must not block a new one, so each
    # attempt gets its own stable sequence number inside the hold.
    prior = db.execute(
        select(PaymentAttempt).where(PaymentAttempt.hold_id == hold.id)
    ).scalars().all()
    attempt_no = max((int(a.attempt_no or 0) for a in prior), default=0) + 1

    attempt = PaymentAttempt(
        booking_id=booking.id,
        hold_id=hold.id,
        customer_id=customer.id,
        attempt_no=attempt_no,
        idempotency_key=_idempotency_key(booking, hold, attempt_no),
        provider="paypal",
        provider_mode=provider.mode,
        expected_amount_cents=booking.price_cents,
        currency=booking.currency,
        status=AttemptStatus.created.value,
    )
    db.add(attempt)
    db.flush()

    try:
        order = provider.create_order(
            attempt_id=attempt.id,
            amount_cents=booking.price_cents,
            currency=booking.currency,
            description=f"{booking.service.name} on {booking.start_utc:%Y-%m-%d}",
            reference=booking.reference,
            idempotency_key=attempt.idempotency_key,
        )
    except ProviderUnavailable as exc:
        attempt.status = AttemptStatus.failed.value
        attempt.failure_reason = exc.code
        db.flush()
        raise

    attempt.provider_order_id = order.order_id
    attempt.raw_status = order.status
    if order.status in {"APPROVED", "COMPLETED"}:
        attempt.status = AttemptStatus.approved.value
    transition(booking, BookingStatus.awaiting_payment.value)
    audit.record(
        db,
        action="payment.order_created",
        actor_id=customer.id,
        actor_role="customer",
        subject_type="payment_attempt",
        subject_id=attempt.id,
        detail={
            "booking_id": booking.id,
            "provider": provider.mode,
            "amount_cents": booking.price_cents,
            "currency": booking.currency,
            "order_id": order.order_id,
        },
        correlation_id=correlation_id,
    )
    return attempt, hold, booking


def _validate_capture(
    settings: Settings,
    attempt: PaymentAttempt,
    order: OrderView,
) -> str | None:
    """Return None when the capture is authoritative, else a machine-readable reason."""
    if order.order_id != attempt.provider_order_id:
        return "ORDER_ID_MISMATCH"
    if order.status not in {"COMPLETED", "APPROVED"}:
        return "ORDER_NOT_COMPLETED"
    if order.status == "APPROVED":
        # Capture accepted but not settled yet: treat as ambiguous, reconcile later.
        return "CAPTURE_PENDING"
    if order.captured_amount_cents is None:
        return "CAPTURE_AMOUNT_MISSING"
    if order.captured_amount_cents != attempt.expected_amount_cents:
        return "AMOUNT_MISMATCH"
    if (order.currency or "").upper() != attempt.currency.upper():
        return "CURRENCY_MISMATCH"
    if order.custom_id and order.custom_id != attempt.id:
        return "CUSTOM_ID_MISMATCH"
    if settings.paypal_merchant_id and order.payee_merchant_id:
        if order.payee_merchant_id != settings.paypal_merchant_id:
            return "MERCHANT_MISMATCH"
    return None


def finalize_capture(
    db: Session,
    settings: Settings,
    *,
    attempt: PaymentAttempt,
    order: OrderView,
    correlation_id: str = "",
    source: str = "capture_api",
) -> PaymentAttempt:
    """Single funnel that records an authoritative capture and settles the booking."""
    now = utcnow()
    problem = _validate_capture(settings, attempt, order)

    if attempt.status in {
        AttemptStatus.reconciled_ok.value,
        AttemptStatus.captured.value,
    }:
        return attempt

    if problem is not None:
        attempt.captured_amount_cents = order.captured_amount_cents
        attempt.raw_status = order.status
        if problem == "CAPTURE_PENDING":
            attempt.status = AttemptStatus.approved.value
            attempt.failure_reason = problem
            db.flush()
            return attempt
        attempt.status = AttemptStatus.reconciled_exception.value
        attempt.failure_reason = problem
        booking = db.get(Booking, attempt.booking_id)
        if booking is not None and booking.status in {
            BookingStatus.held.value,
            BookingStatus.awaiting_payment.value,
        }:
            transition(booking, BookingStatus.payment_exception.value, reason=problem)
            booking.needs_attention = True
        audit.record(
            db,
            action="payment.capture_rejected",
            subject_type="payment_attempt",
            subject_id=attempt.id,
            detail={"reason": problem, "source": source},
            correlation_id=correlation_id,
        )
        db.flush()
        return attempt

    attempt.status = AttemptStatus.captured.value
    attempt.provider_capture_id = order.capture_id
    attempt.captured_amount_cents = order.captured_amount_cents
    attempt.captured_at = now
    attempt.raw_status = order.status
    attempt.failure_reason = ""

    booking = db.get(Booking, attempt.booking_id)
    hold = db.get(Hold, attempt.hold_id)
    if booking is None or hold is None:
        attempt.status = AttemptStatus.reconciled_exception.value
        attempt.failure_reason = "BOOKING_MISSING"
        db.flush()
        return attempt

    payable = booking.status in {BookingStatus.held.value, BookingStatus.awaiting_payment.value}
    slot_still_valid = hold.status == HoldStatus.active.value and hold.expires_at > now

    if payable and slot_still_valid:
        # Only re-point capacity once we know the booking may still be confirmed.
        # Re-pointing first and releasing afterwards is how a cancelled booking
        # used to lose a technician's capacity permanently.
        try:
            for block in db.execute(
                select(availability.SlotBlock).where(
                    availability.SlotBlock.owner_kind == "hold",
                    availability.SlotBlock.owner_id == hold.id,
                    availability.SlotBlock.active == 1,
                )
            ).scalars().all():
                block.owner_kind = "booking"
                block.owner_id = booking.id
            db.flush()
        except IntegrityError:  # pragma: no cover - defensive
            db.rollback()
            slot_still_valid = False

    if payable and slot_still_valid:
        hold.status = HoldStatus.consumed.value
        transition(booking, BookingStatus.confirmed.value)
        booking.needs_attention = False
        attempt.status = AttemptStatus.reconciled_ok.value
    else:
        # Money was captured but the appointment cannot stand. Record the money,
        # release whatever capacity this hold still owns, and surface a task.
        if hold.status == HoldStatus.active.value:
            hold.status = HoldStatus.expired.value
        availability.release_cells(db, "hold", hold.id)
        if payable:
            transition(
                booking,
                BookingStatus.payment_exception.value,
                reason="CAPTURED_AFTER_HOLD_EXPIRED",
            )
            booking.needs_attention = True
        elif booking.status in {
            BookingStatus.cancelled.value,
            BookingStatus.expired.value,
            BookingStatus.payment_exception.value,
        }:
            # A late COMPLETED after DENIED/cancel: keep the money visible on the
            # booking so an operator can act, but never resurrect the appointment.
            booking.needs_attention = True
            if not booking.exception_reason:
                booking.exception_reason = "CAPTURED_ON_CLOSED_BOOKING"
        attempt.status = AttemptStatus.reconciled_exception.value
        attempt.failure_reason = (
            "CAPTURED_AFTER_HOLD_EXPIRED" if payable else "CAPTURED_ON_CLOSED_BOOKING"
        )

    audit.record(
        db,
        action="payment.capture_verified",
        subject_type="payment_attempt",
        subject_id=attempt.id,
        detail={
            "booking_id": booking.id,
            "amount_cents": attempt.captured_amount_cents,
            "currency": attempt.currency,
            "source": source,
            "outcome": attempt.status,
        },
        correlation_id=correlation_id,
    )
    db.flush()
    return attempt


def capture(
    db: Session,
    settings: Settings,
    provider: PaymentProvider,
    *,
    customer: User,
    attempt_id: str,
    correlation_id: str = "",
) -> PaymentAttempt:
    attempt = db.execute(select(PaymentAttempt).where(PaymentAttempt.id == attempt_id)).scalar_one_or_none()
    if attempt is None or attempt.customer_id != customer.id:
        raise NotFound("Payment attempt")

    if attempt.status in {AttemptStatus.reconciled_ok.value, AttemptStatus.captured.value}:
        return attempt
    if attempt.status == AttemptStatus.reconciled_exception.value:
        return attempt
    if attempt.status in {AttemptStatus.cancelled.value, AttemptStatus.failed.value}:
        raise Conflict("PAYMENT_NOT_ACTIVE", "This payment attempt is closed.")
    if not attempt.provider_order_id:
        raise Conflict("PAYMENT_NOT_READY", "The provider order was never created.")

    order = provider.capture_order(attempt.provider_order_id, idempotency_key=_capture_key(attempt))
    return finalize_capture(db, settings, attempt=attempt, order=order, correlation_id=correlation_id)


def reconcile(
    db: Session,
    settings: Settings,
    provider: PaymentProvider,
    *,
    attempt: PaymentAttempt,
    correlation_id: str = "",
    source: str = "reconcile",
) -> PaymentAttempt:
    if attempt.status in {AttemptStatus.reconciled_ok.value, AttemptStatus.reconciled_exception.value}:
        return attempt
    if not attempt.provider_order_id:
        raise Conflict("PAYMENT_NOT_READY", "Nothing to reconcile: no provider order.")
    order = provider.get_order(attempt.provider_order_id)
    return finalize_capture(db, settings, attempt=attempt, order=order, correlation_id=correlation_id, source=source)


def cancel_checkout(
    db: Session,
    provider: PaymentProvider,
    *,
    customer: User,
    attempt_id: str,
    correlation_id: str = "",
) -> PaymentAttempt:
    attempt = db.execute(select(PaymentAttempt).where(PaymentAttempt.id == attempt_id)).scalar_one_or_none()
    if attempt is None or attempt.customer_id != customer.id:
        raise NotFound("Payment attempt")
    if attempt.status in {AttemptStatus.reconciled_ok.value, AttemptStatus.captured.value}:
        raise Conflict("PAYMENT_ALREADY_CAPTURED", "This payment already succeeded; it cannot be cancelled.")
    cancel_fn = getattr(provider, "cancel_order", None)
    if callable(cancel_fn) and attempt.provider_order_id:
        try:
            cancel_fn(attempt.provider_order_id)
        except PaymentError:
            pass
        except Exception:  # pragma: no cover - provider safety
            log.warning("provider cancel failed for attempt=%s", attempt.id)
    attempt.status = AttemptStatus.cancelled.value
    hold = db.get(Hold, attempt.hold_id)
    if hold is not None:
        release_hold(db, hold, reason="Checkout cancelled")
    audit.record(
        db,
        action="payment.checkout_cancelled",
        actor_id=customer.id,
        actor_role="customer",
        subject_type="payment_attempt",
        subject_id=attempt.id,
        correlation_id=correlation_id,
    )
    db.flush()
    return attempt


# ------------------------------------------------------------------ webhooks
def _order_from_verified_event(event: dict, attempt: PaymentAttempt) -> OrderView | None:
    """Build a capture view from a signature-verified webhook resource.

    A verified PAYMENT.CAPTURE.COMPLETED event is authoritative evidence of capture.
    We still derive the amounts from the event so normal validation applies.
    """
    resource = event.get("resource") or {}
    if str(resource.get("status", "")).upper() != "COMPLETED":
        return None
    amount = resource.get("amount") or {}
    try:
        from decimal import Decimal

        minor = int((Decimal(str(amount.get("value"))) * 100).to_integral_value())
    except Exception:
        return None
    return OrderView(
        order_id=attempt.provider_order_id or "",
        status="COMPLETED",
        approve_url=None,
        capture_id=resource.get("id"),
        captured_amount_cents=minor,
        currency=str(amount.get("currency_code", "")),
        payee_merchant_id=(resource.get("payee") or {}).get("merchant_id"),
        custom_id=resource.get("custom_id"),
        invoice_id=resource.get("invoice_id"),
        raw={"source": "verified_webhook_event"},
    )


def handle_payment_event(
    db: Session,
    settings: Settings,
    provider: PaymentProvider,
    *,
    event: dict,
    event_id: str,
    signature_verified: bool,
    event_type: str = "",
    correlation_id: str = "",
) -> str:
    """Idempotent webhook application. Signature must be verified by the caller."""
    if not signature_verified:
        return "rejected_signature"
    existing = db.get(ProcessedPaymentEvent, event_id)
    if existing is not None:
        return "duplicate"

    db.add(
        ProcessedPaymentEvent(
            event_id=event_id,
            event_type=event_type,
            signature_verified=True,
            note="received",
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"

    resource = (event.get("resource") or {})
    order_id = None
    if resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id"):
        order_id = resource["supplementary_data"]["related_ids"]["order_id"]
    elif str(resource.get("id", "")).startswith(("SIMORDER", "ORDER", "5O1")) and event_type.startswith("PAYMENT.CAPTURE"):
        order_id = resource.get("id")
    elif resource.get("id") and event_type.startswith("CHECKOUT.ORDER"):
        order_id = resource["id"]

    attempt = None
    if order_id:
        attempt = db.execute(
            select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
        ).scalar_one_or_none()
    if attempt is None:
        db.get(ProcessedPaymentEvent, event_id).note = "no_matching_attempt"
        db.flush()
        return "ignored_unknown_order"

    if event_type in {"PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.COMPLETED"}:
        try:
            view = None
            try:
                order = provider.get_order(attempt.provider_order_id or "")
                if order.status == "COMPLETED":
                    view = order
            except (ProviderUnavailable, PaymentError):
                view = None
            if view is None:
                # The order has not settled yet in PayPal's read model; the verified
                # event itself carries the authoritative capture facts.
                view = _order_from_verified_event(event, attempt)
            if view is None:
                db.get(ProcessedPaymentEvent, event_id).note = "reconcile_deferred"
                db.flush()
                return "deferred"
            finalize_capture(
                db, settings, attempt=attempt, order=view,
                correlation_id=correlation_id, source=f"webhook:{event_type}",
            )
        except (ProviderUnavailable, PaymentError):
            db.get(ProcessedPaymentEvent, event_id).note = "reconcile_deferred"
            db.flush()
            return "deferred"
        db.get(ProcessedPaymentEvent, event_id).note = f"applied:{attempt.status}"
        db.flush()
        return "applied"

    if event_type in {"PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUSED"}:
        attempt.status = AttemptStatus.failed.value
        attempt.failure_reason = event_type
        booking = db.get(Booking, attempt.booking_id)
        if booking is not None and booking.status == BookingStatus.awaiting_payment.value:
            transition(booking, BookingStatus.cancelled.value, reason=event_type)
            booking.needs_attention = True
        # Free the capacity immediately; a later COMPLETED for the same order must
        # not find cells still attached to this hold.
        hold = db.get(Hold, attempt.hold_id)
        if hold is not None and hold.status == HoldStatus.active.value:
            release_hold(db, hold, reason=event_type)
        db.get(ProcessedPaymentEvent, event_id).note = "denied"
        db.flush()
        return "applied"

    db.get(ProcessedPaymentEvent, event_id).note = "ignored_type"
    db.flush()
    return "ignored_type"
