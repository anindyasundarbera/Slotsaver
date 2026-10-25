from __future__ import annotations

from datetime import date, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..deps import customer_session, demo_day, get_db, provider_dep, settings_dep
from ..errors import NotFound
from ..models import AuthSession, Booking, BookingStatus, PaymentAttempt
from ..schemas import (
    AvailabilityQuery,
    BookingOut,
    CheckoutOut,
    HoldCreate,
    HoldOut,
    OptionOut,
    ReassignmentApprove,
    ReassignmentDecline,
)
from ..security import limiter
from ..services import availability, bookings as booking_service, serializers
from ..services.payments import PaymentProvider

router = APIRouter(prefix="/api", tags=["customer"])


@router.get("/availability", response_model=list[OptionOut])
def get_availability(
    service_code: str = Query(min_length=2, max_length=40),
    day: date = Query(...),
    after_local: str | None = Query(default=None, max_length=5),
    before_local: str | None = Query(default=None, max_length=5),
    max_price_cents: int | None = Query(default=None, ge=0, le=100_000),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
) -> list[OptionOut]:
    from ..models import Service

    availability.expire_stale_holds(db, utcnow())
    service = db.execute(select(Service).where(Service.code == service_code)).scalar_one_or_none()
    if service is None:
        raise NotFound("Service")
    try:
        candidates = availability.find_candidates(
            db, settings, service, day, after=after_local, before=before_local
        )
    except ValueError as exc:
        from ..errors import Validation

        raise Validation(str(exc)) from exc
    options = [
        serializers.build_option(
            service=service,
            technician=c.technician,
            start_utc=c.start_utc,
            end_utc=c.end_utc,
            settings=settings,
            budget_cents=max_price_cents,
        )
        for c in candidates
    ]
    if max_price_cents is not None:
        options = [o for o in options if o.within_budget]
    return options[:12]


@router.post("/holds", response_model=HoldOut, status_code=201)
def create_hold(
    payload: HoldCreate,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
) -> HoldOut:
    hold, booking = booking_service.create_hold(
        db,
        settings,
        customer=session.user,
        service_code=payload.service_code,
        technician_id=payload.technician_id,
        start_utc=payload.start_utc,
        notes=payload.notes,
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return serializers.hold_out(db, hold, settings, utcnow())


@router.get("/holds/{hold_id}", response_model=HoldOut)
def read_hold(
    hold_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
) -> HoldOut:
    from ..models import Hold

    availability.expire_stale_holds(db, utcnow())
    hold = db.get(Hold, hold_id)
    if hold is None or hold.customer_id != session.user_id:
        raise NotFound("Hold")
    return serializers.hold_out(db, hold, settings, utcnow())


@router.delete("/holds/{hold_id}", response_model=BookingOut)
def delete_hold(
    hold_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
) -> BookingOut:
    booking = booking_service.cancel_hold(
        db, customer=session.user, hold_id=hold_id, correlation_id=request.state.correlation_id
    )
    db.commit()
    db.refresh(booking)
    return serializers.booking_out(db, booking, settings)


@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
) -> list[BookingOut]:
    availability.expire_stale_holds(db, utcnow())
    rows = db.execute(
        select(Booking)
        .where(Booking.customer_id == session.user_id)
        .order_by(Booking.start_utc.desc())
        .limit(50)
    ).scalars().all()
    db.commit()
    return [serializers.booking_out(db, b, settings) for b in rows]


@router.get("/bookings/{booking_id}", response_model=BookingOut)
def read_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
) -> BookingOut:
    availability.expire_stale_holds(db, utcnow())
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_id != session.user_id:
        raise NotFound("Booking")
    db.commit()
    return serializers.booking_out(db, booking, settings)


# ------------------------------------------------------------------ payment
@router.post("/holds/{hold_id}/checkout", response_model=CheckoutOut, status_code=201)
def start_checkout(
    hold_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    provider: PaymentProvider = Depends(provider_dep),
    session: AuthSession = Depends(customer_session),
) -> CheckoutOut:
    limiter.payment.check(f"checkout:{session.user_id}")
    attempt, hold, booking = booking_service.start_checkout(
        db,
        settings,
        provider,
        customer=session.user,
        hold_id=hold_id,
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return CheckoutOut(
        attempt_id=attempt.id,
        booking_id=booking.id,
        status=attempt.status,
        provider_mode=attempt.provider_mode,
        amount_cents=attempt.expected_amount_cents,
        currency=attempt.currency,
        approve_url=(
            f"/simulated-checkout?order={attempt.provider_order_id}"
            if attempt.provider_mode == "simulated" and attempt.provider_order_id
            else _approve_url(provider, attempt.provider_order_id)
        ),
        simulated_token=attempt.provider_order_id if attempt.provider_mode == "simulated" else None,
        expires_at=hold.expires_at,
    )


def _approve_url(provider: PaymentProvider, order_id: str | None) -> str | None:
    if not order_id:
        return None
    try:
        order = provider.get_order(order_id)
    except Exception:
        return None
    return order.approve_url


@router.post("/payments/{attempt_id}/capture")
def capture_payment(
    attempt_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    provider: PaymentProvider = Depends(provider_dep),
    session: AuthSession = Depends(customer_session),
):
    limiter.payment.check(f"capture:{session.user_id}")
    attempt = booking_service.capture(
        db,
        settings,
        provider,
        customer=session.user,
        attempt_id=attempt_id,
        correlation_id=request.state.correlation_id,
    )
    booking = db.get(Booking, attempt.booking_id)
    db.commit()
    return serializers.payment_out(attempt, booking)


@router.post("/payments/{attempt_id}/cancel")
def cancel_payment(
    attempt_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    provider: PaymentProvider = Depends(provider_dep),
    session: AuthSession = Depends(customer_session),
):
    limiter.payment.check(f"cancel:{session.user_id}")
    attempt = booking_service.cancel_checkout(
        db,
        provider,
        customer=session.user,
        attempt_id=attempt_id,
        correlation_id=request.state.correlation_id,
    )
    booking = db.get(Booking, attempt.booking_id)
    db.commit()
    return serializers.payment_out(attempt, booking)


@router.get("/payments/{attempt_id}")
def read_payment(
    attempt_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
):
    attempt = db.get(PaymentAttempt, attempt_id)
    if attempt is None or attempt.customer_id != session.user_id:
        raise NotFound("Payment attempt")
    booking = db.get(Booking, attempt.booking_id)
    return serializers.payment_out(attempt, booking)


# ------------------------------------------------------------------ simulated checkout
@router.post("/simulated-checkout/{order_id}/approve")
def simulate_approve(
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    provider: PaymentProvider = Depends(provider_dep),
    session: AuthSession = Depends(customer_session),
):
    if settings.paypal_mode != "simulated":
        raise NotFound("Simulated checkout")
    attempt = db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.provider_order_id == order_id,
            PaymentAttempt.customer_id == session.user_id,
        )
    ).scalar_one_or_none()
    if attempt is None:
        raise NotFound("Order")
    approve = getattr(provider, "approve", None)
    if not callable(approve):
        raise NotFound("Order")
    order = approve(order_id)
    return {"order_id": order.order_id, "status": order.status, "simulated": True}


@router.post("/simulated-checkout/{order_id}/decline")
def simulate_decline(
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    provider: PaymentProvider = Depends(provider_dep),
    session: AuthSession = Depends(customer_session),
):
    if settings.paypal_mode != "simulated":
        raise NotFound("Simulated checkout")
    attempt = db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.provider_order_id == order_id,
            PaymentAttempt.customer_id == session.user_id,
        )
    ).scalar_one_or_none()
    if attempt is None:
        raise NotFound("Order")
    cancel = getattr(provider, "cancel_order", None)
    if callable(cancel):
        cancel(order_id)
    return {"order_id": order_id, "status": "VOIDED", "simulated": True}


# ------------------------------------------------------------------ reassignment
@router.post("/bookings/{booking_id}/reassignment/approve", response_model=BookingOut)
def approve_reassignment(
    booking_id: str,
    payload: ReassignmentApprove,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
):
    from ..services import reassignment

    booking = reassignment.approve_reassignment(
        db,
        settings,
        customer=session.user,
        booking_id=booking_id,
        proposal_id=payload.proposal_id,
        technician_id=payload.technician_id,
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    db.refresh(booking)
    return serializers.booking_out(db, booking, settings)


@router.post("/bookings/{booking_id}/reassignment/decline", response_model=BookingOut)
def decline_reassignment(
    booking_id: str,
    payload: ReassignmentDecline,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(customer_session),
):
    from ..services import reassignment

    booking = reassignment.decline_reassignment(
        db,
        customer=session.user,
        booking_id=booking_id,
        proposal_id=payload.proposal_id,
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    db.refresh(booking)
    return serializers.booking_out(db, booking, settings)
