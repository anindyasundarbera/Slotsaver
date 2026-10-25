from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..errors import Conflict, NotFound
from ..models import (
    Booking,
    BookingStatus,
    ProposalStatus,
    ReassignmentProposal,
    Service,
    Technician,
    TechnicianBlock,
    User,
)
from ..timeutil import slot_starts
from . import audit, availability


def _candidate_list(
    db: Session, settings: Settings, booking: Booking, original_technician_id: str
) -> list[dict]:
    service = db.get(Service, booking.service_id)
    technicians = db.execute(
        select(Technician).where(Technician.active.is_(True)).order_by(Technician.name)
    ).scalars().all()
    out: list[dict] = []
    for tech in technicians:
        if tech.id == original_technician_id:
            continue
        if service is None or service.required_skill not in (tech.skills or []):
            continue
        free = availability.is_window_free(db, tech.id, booking.start_utc, booking.end_utc)
        out.append(
            {
                "technician_id": tech.id,
                "technician_name": tech.name,
                "technician_color": tech.color,
                "available": free,
                "note": "Same time, same price" if free else "Already booked at this time",
            }
        )
    return out


def mark_unavailable(
    db: Session,
    settings: Settings,
    *,
    owner: User,
    technician_id: str,
    start_utc: datetime,
    end_utc: datetime,
    reason: str,
    correlation_id: str = "",
) -> dict:
    now = utcnow()
    availability.expire_stale_holds(db, now)
    technician = db.get(Technician, technician_id)
    if technician is None or not technician.active:
        raise NotFound("Technician")
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise Conflict("INVALID_WINDOW", "Unavailability window must include a timezone offset.")
    start_utc = start_utc.astimezone(timezone.utc)
    end_utc = end_utc.astimezone(timezone.utc)
    if end_utc <= start_utc:
        raise Conflict("INVALID_WINDOW", "End must be after start.")
    if end_utc - start_utc > timedelta(days=14):
        raise Conflict("WINDOW_TOO_LARGE", "Unavailability window must be 14 days or less.")

    overlapping = db.execute(
        select(TechnicianBlock).where(
            TechnicianBlock.technician_id == technician_id,
            TechnicianBlock.start_utc < end_utc,
            TechnicianBlock.end_utc > start_utc,
        )
    ).scalars().first()
    if overlapping is not None:
        raise Conflict("BLOCK_OVERLAP", "This technician already has unavailability in that window.")

    block = TechnicianBlock(
        technician_id=technician_id,
        start_utc=start_utc,
        end_utc=end_utc,
        reason=reason[:200],
        created_by=owner.id,
    )
    db.add(block)
    db.flush()

    affected = db.execute(
        select(Booking)
        .where(
            Booking.technician_id == technician_id,
            Booking.status.in_(
                [
                    BookingStatus.confirmed.value,
                    BookingStatus.payment_exception.value,
                ]
            ),
            Booking.start_utc < end_utc,
            Booking.end_utc > start_utc,
        )
        .order_by(Booking.start_utc)
    ).scalars().all()

    proposals: list[str] = []
    unresolved: list[str] = []
    for booking in affected:
        candidates = _candidate_list(db, settings, booking, technician_id)
        available = [c for c in candidates if c["available"]]
        status = ProposalStatus.proposed.value if available else ProposalStatus.unresolved.value
        proposal = ReassignmentProposal(
            booking_id=booking.id,
            original_technician_id=technician_id,
            candidates=candidates,
            status=status,
            reason=reason[:200],
            created_by=owner.id,
        )
        db.add(proposal)
        db.flush()
        proposals.append(proposal.id)
        if status == ProposalStatus.unresolved.value:
            unresolved.append(booking.id)
        if booking.status == BookingStatus.confirmed.value:
            booking.status = BookingStatus.needs_reassignment.value
            booking.exception_reason = reason[:200]
        booking.needs_attention = True

    audit.record(
        db,
        action="owner.technician_unavailable",
        actor_id=owner.id,
        actor_role="owner",
        subject_type="technician",
        subject_id=technician_id,
        detail={
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "reason": reason,
            "affected": len(affected),
            "unresolved": len(unresolved),
        },
        correlation_id=correlation_id,
    )
    db.flush()
    return {
        "block_id": block.id,
        "technician_id": technician_id,
        "technician_name": technician.name,
        "affected_booking_ids": [b.id for b in affected],
        "proposals_created": proposals,
        "unresolved_booking_ids": unresolved,
    }


def approve_reassignment(
    db: Session,
    settings: Settings,
    *,
    customer: User,
    booking_id: str,
    proposal_id: str,
    technician_id: str,
    correlation_id: str = "",
) -> Booking:
    now = utcnow()
    availability.expire_stale_holds(db, now)
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_id != customer.id:
        raise NotFound("Booking")
    if booking.status != BookingStatus.needs_reassignment.value:
        raise Conflict("BOOKING_NOT_AWAITING_REASSIGNMENT", "This booking does not need reassignment.")
    proposal = db.get(ReassignmentProposal, proposal_id)
    if proposal is None or proposal.booking_id != booking.id:
        raise NotFound("Proposal")
    if proposal.status not in {ProposalStatus.proposed.value, ProposalStatus.declined.value}:
        raise Conflict("PROPOSAL_CLOSED", "This proposal is no longer open.")
    candidate = next(
        (c for c in (proposal.candidates or []) if c.get("technician_id") == technician_id), None
    )
    if candidate is None:
        raise Conflict("CANDIDATE_NOT_OFFERED", "That technician was not offered for this booking.")
    if not candidate.get("available"):
        raise Conflict("CANDIDATE_UNAVAILABLE", "That technician is not free at this time.")

    # Re-validate atomically: release the old cells and claim new ones in one transaction.
    try:
        availability.release_cells(db, "booking", booking.id)
        availability.claim_cells(db, technician_id, booking.start_utc, booking.end_utc, "booking", booking.id)
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "SLOT_UNAVAILABLE", "The replacement slot was taken while you were deciding."
        ) from exc

    previous_technician = booking.technician_id
    booking.technician_id = technician_id
    booking.status = BookingStatus.confirmed.value
    booking.exception_reason = ""
    booking.needs_attention = False
    booking.confirmed_at = booking.confirmed_at or now
    proposal.status = ProposalStatus.accepted.value
    proposal.accepted_technician_id = technician_id
    proposal.resolved_at = now
    db.flush()

    audit.record(
        db,
        action="reassignment.approved",
        actor_id=customer.id,
        actor_role="customer",
        subject_type="booking",
        subject_id=booking.id,
        detail={
            "from_technician_id": previous_technician,
            "to_technician_id": technician_id,
            "proposal_id": proposal.id,
        },
        correlation_id=correlation_id,
    )
    return booking


def decline_reassignment(
    db: Session,
    *,
    customer: User,
    booking_id: str,
    proposal_id: str,
    correlation_id: str = "",
) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_id != customer.id:
        raise NotFound("Booking")
    proposal = db.get(ReassignmentProposal, proposal_id)
    if proposal is None or proposal.booking_id != booking.id:
        raise NotFound("Proposal")
    if proposal.status != ProposalStatus.proposed.value:
        raise Conflict("PROPOSAL_CLOSED", "This proposal is no longer open.")
    proposal.status = ProposalStatus.declined.value
    proposal.resolved_at = utcnow()
    booking.needs_attention = True
    booking.exception_reason = "Customer declined the proposed replacement"
    audit.record(
        db,
        action="reassignment.declined",
        actor_id=customer.id,
        actor_role="customer",
        subject_type="booking",
        subject_id=booking.id,
        detail={"proposal_id": proposal.id},
        correlation_id=correlation_id,
    )
    db.flush()
    return booking
