from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..deps import demo_day, get_db, owner_session, settings_dep
from ..errors import Conflict, NotFound, Validation
from ..models import AuthSession, Booking, BookingStatus
from ..schemas import (
    AnalyticsOut,
    BookingOut,
    DisruptionResult,
    ResolveExceptionIn,
    TimelineOut,
    UnavailableIn,
)
from ..services import bookings as booking_service, owner as owner_service, reassignment, serializers

router = APIRouter(prefix="/api/owner", tags=["owner"])


@router.get("/timeline", response_model=TimelineOut)
def get_timeline(
    day: date | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(owner_session),
) -> TimelineOut:
    target = day or demo_day(db, settings)
    result = owner_service.timeline(db, settings, target)
    db.commit()
    return result


@router.get("/analytics", response_model=AnalyticsOut)
def get_analytics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(owner_session),
) -> AnalyticsOut:
    today = demo_day(db, settings)
    start = date_from or (today - timedelta(days=6))
    end = date_to or (today + timedelta(days=7))
    try:
        result = owner_service.analytics(db, settings, start, end)
    except ValueError as exc:
        raise Validation(str(exc)) from exc
    db.commit()
    return result


@router.get("/bookings", response_model=list[BookingOut])
def list_all_bookings(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(owner_session),
) -> list[BookingOut]:
    from ..services import availability

    availability.expire_stale_holds(db, utcnow())
    query = select(Booking).order_by(Booking.start_utc.desc()).limit(200)
    if status_filter:
        target = status_filter if status_filter in BookingStatus.__members__ else None
        if target is None:
            raise Validation("Unknown status filter.")
        query = query.where(Booking.status == BookingStatus[target].value)
    rows = db.execute(query).scalars().all()
    db.commit()
    return [serializers.booking_out(db, b, settings) for b in rows]


@router.post("/technicians/{technician_id}/unavailable", response_model=DisruptionResult)
def mark_unavailable(
    technician_id: str,
    payload: UnavailableIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(owner_session),
) -> DisruptionResult:
    result = reassignment.mark_unavailable(
        db,
        settings,
        owner=session.user,
        technician_id=technician_id,
        start_utc=payload.start_utc,
        end_utc=payload.end_utc,
        reason=payload.reason,
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return DisruptionResult(**result)


@router.post("/bookings/{booking_id}/resolve-exception", response_model=BookingOut)
def resolve_exception(
    booking_id: str,
    payload: ResolveExceptionIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(owner_session),
) -> BookingOut:
    from ..services import availability, audit

    availability.expire_stale_holds(db, utcnow())
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise NotFound("Booking")
    if booking.status != BookingStatus.payment_exception.value:
        raise Conflict("NOT_AN_EXCEPTION", "This booking is not in a payment exception state.")
    if payload.resolution == "cancelled":
        booking_service.transition(
            booking, BookingStatus.cancelled.value, reason="Owner resolved exception: cancelled"
        )
        availability.release_cells(db, "booking", booking.id)
    else:
        # Manual confirmation is an explicit owner override; it never creates a
        # payment record. It still has to win the capacity claim, otherwise the
        # override would silently double-book the technician.
        from sqlalchemy.exc import IntegrityError

        try:
            availability.claim_cells(
                db, booking.technician_id, booking.start_utc, booking.end_utc, "booking", booking.id
            )
        except IntegrityError as exc:
            db.rollback()
            raise Conflict(
                "SLOT_UNAVAILABLE",
                "That time is now taken by another reservation, so it cannot be force-confirmed. "
                "Cancel the booking and rebook instead.",
            ) from exc
        booking_service.transition(
            booking, BookingStatus.confirmed.value, reason="Owner resolved exception: confirmed"
        )
    booking.needs_attention = False
    audit.record(
        db,
        action="owner.exception_resolved",
        actor_id=session.user_id,
        actor_role="owner",
        subject_type="booking",
        subject_id=booking.id,
        detail={"resolution": payload.resolution, "note": payload.note},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    db.refresh(booking)
    return serializers.booking_out(db, booking, settings)


@router.get("/audit", response_model=list[dict])
def read_audit(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
    session: AuthSession = Depends(owner_session),
) -> list[dict]:
    from ..models import AuditEvent

    rows = db.execute(
        select(AuditEvent).order_by(AuditEvent.at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "at": r.at.isoformat(),
            "action": r.action,
            "actor_role": r.actor_role,
            "subject_type": r.subject_type,
            "subject_id": r.subject_id,
            "detail": r.detail,
        }
        for r in rows
    ]


@router.post("/demo/reset")
def reset_demo(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    session: AuthSession = Depends(owner_session),
) -> dict:
    """Restore the synthetic fixtures. Never touches a non-demo database."""
    from ..seed import seed_database
    from ..services import audit

    if not settings.allow_demo_reset:
        raise Conflict("RESET_DISABLED", "Demo reset is disabled by configuration.")
    summary = seed_database(db, settings)
    audit.record(
        db,
        action="owner.demo_reset",
        actor_id=session.user_id,
        actor_role="owner",
        subject_type="database",
        subject_id="demo",
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return {"reset": True, **summary}
