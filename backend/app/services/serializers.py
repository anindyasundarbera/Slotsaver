from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Booking, BookingStatus, Hold, PaymentAttempt, ProposalStatus, ReassignmentProposal
from ..schemas import (
    BookingOut,
    HoldOut,
    OptionOut,
    PaymentOut,
    ProposalCandidate,
    ProposalOut,
)
from ..timeutil import tz_label
from .bookings import STATUS_LABELS


def local_pair(start_utc, end_utc, settings: Settings) -> tuple[str, str, str]:
    tz = settings.tz
    return (
        start_utc.astimezone(tz).strftime("%a %d %b %Y, %-I:%M %p"),
        end_utc.astimezone(tz).strftime("%-I:%M %p"),
        tz_label(tz, start_utc),
    )


def build_option(
    *,
    service,
    technician,
    start_utc,
    end_utc,
    settings: Settings,
    budget_cents: int | None,
) -> OptionOut:
    start_local, end_local, label = local_pair(start_utc, end_utc, settings)
    return OptionOut(
        option_id=f"{technician.id}|{service.code}|{start_utc.isoformat()}",
        technician_id=technician.id,
        technician_name=technician.name,
        technician_color=technician.color,
        service_id=service.id,
        service_code=service.code,
        service_name=service.name,
        start_utc=start_utc,
        end_utc=end_utc,
        start_local=start_local,
        end_local=end_local,
        timezone_label=label,
        price_cents=service.price_cents,
        currency=service.currency,
        duration_minutes=service.duration_minutes,
        within_budget=budget_cents is None or service.price_cents <= budget_cents,
    )


def hold_out(db: Session, hold: Hold, settings: Settings, now) -> HoldOut:
    booking = db.execute(select(Booking).where(Booking.hold_id == hold.id)).scalar_one()
    start_local, end_local, label = local_pair(hold.start_utc, hold.end_utc, settings)
    remaining = max(0, int((hold.expires_at - now).total_seconds()))
    return HoldOut(
        id=hold.id,
        status=hold.status,
        technician_id=hold.technician_id,
        technician_name=hold.technician.name,
        service_name=hold.service.name,
        start_utc=hold.start_utc,
        end_utc=hold.end_utc,
        start_local=start_local,
        end_local=end_local,
        timezone_label=label,
        price_cents=hold.price_cents,
        currency=hold.currency,
        expires_at=hold.expires_at,
        seconds_remaining=remaining,
        booking_id=booking.id,
    )


def proposal_out(proposal: ReassignmentProposal) -> ProposalOut:
    return ProposalOut(
        id=proposal.id,
        status=proposal.status,
        reason=proposal.reason,
        original_technician_id=proposal.original_technician_id,
        created_at=proposal.created_at,
        candidates=[
            ProposalCandidate(
                technician_id=c.get("technician_id", ""),
                technician_name=c.get("technician_name", ""),
                technician_color=c.get("technician_color", "#64748b"),
                available=bool(c.get("available")),
                note=c.get("note", ""),
            )
            for c in (proposal.candidates or [])
        ],
    )


def booking_out(
    db: Session,
    booking: Booking,
    settings: Settings,
    *,
    include_proposal: bool = True,
) -> BookingOut:
    attempt = db.execute(
        select(PaymentAttempt)
        .where(PaymentAttempt.booking_id == booking.id)
        .order_by(PaymentAttempt.created_at.desc())
    ).scalars().first()
    start_local, end_local, label = local_pair(booking.start_utc, booking.end_utc, settings)
    proposal = None
    if include_proposal:
        row = db.execute(
            select(ReassignmentProposal)
            .where(
                ReassignmentProposal.booking_id == booking.id,
                ReassignmentProposal.status.in_(
                    [ProposalStatus.proposed.value, ProposalStatus.unresolved.value]
                ),
            )
            .order_by(ReassignmentProposal.created_at.desc())
        ).scalars().first()
        if row is not None:
            proposal = proposal_out(row)
    return BookingOut(
        id=booking.id,
        reference=booking.reference,
        status=BookingStatus(booking.status),
        status_label=STATUS_LABELS.get(booking.status, booking.status),
        technician_id=booking.technician_id,
        technician_name=booking.technician.name,
        technician_color=booking.technician.color,
        service_name=booking.service.name,
        service_code=booking.service.code,
        start_utc=booking.start_utc,
        end_utc=booking.end_utc,
        start_local=start_local,
        end_local=end_local,
        timezone_label=label,
        price_cents=booking.price_cents,
        currency=booking.currency,
        notes=booking.notes,
        customer_name=booking.customer.display_name,
        needs_attention=booking.needs_attention,
        exception_reason=booking.exception_reason,
        created_at=booking.created_at,
        confirmed_at=booking.confirmed_at,
        payment_status=attempt.status if attempt else None,
        proposal=proposal,
    )


def payment_out(attempt: PaymentAttempt, booking: Booking) -> PaymentOut:
    return PaymentOut(
        attempt_id=attempt.id,
        booking_id=attempt.booking_id,
        status=attempt.status,
        provider_mode=attempt.provider_mode,
        amount_cents=attempt.expected_amount_cents,
        captured_amount_cents=attempt.captured_amount_cents,
        currency=attempt.currency,
        failure_reason=attempt.failure_reason,
        booking_status=booking.status,
    )
