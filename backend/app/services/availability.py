from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import Conflict
from ..models import Booking, BookingStatus, Hold, HoldStatus, Service, SlotBlock, Technician, TechnicianBlock
from ..timeutil import (
    SLOT_MINUTES,
    is_business_open,
    local_instant,
    slot_starts,
)

ACTIVE_BOOKING_STATUSES = {
    BookingStatus.held.value,
    BookingStatus.awaiting_payment.value,
    BookingStatus.confirmed.value,
    BookingStatus.needs_reassignment.value,
    BookingStatus.payment_exception.value,
}


@dataclass(frozen=True)
class Candidate:
    technician: Technician
    start_utc: datetime
    end_utc: datetime


def parse_hhmm(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("time must look like HH:MM")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and mm in (0, 30)):
        raise ValueError("time must be on the half hour")
    return hh, mm


def claimed_cells(db: Session, technician_id: str, start_utc: datetime, end_utc: datetime) -> set[datetime]:
    starts = slot_starts(start_utc, end_utc)
    rows = db.execute(
        select(SlotBlock.slot_start_utc).where(
            SlotBlock.technician_id == technician_id,
            SlotBlock.active == 1,
            SlotBlock.slot_start_utc.in_(starts),
        )
    ).scalars().all()
    return set(rows)


def technician_busy_map(
    db: Session, technician_ids: list[str], day_start_utc: datetime, day_end_utc: datetime
) -> dict[str, set[datetime]]:
    if not technician_ids:
        return {}
    rows = db.execute(
        select(SlotBlock.technician_id, SlotBlock.slot_start_utc).where(
            SlotBlock.technician_id.in_(technician_ids),
            SlotBlock.active == 1,
            SlotBlock.slot_start_utc >= day_start_utc,
            SlotBlock.slot_start_utc < day_end_utc,
        )
    ).all()
    busy: dict[str, set[datetime]] = {tid: set() for tid in technician_ids}
    for technician_id, slot in rows:
        busy.setdefault(technician_id, set()).add(slot)
    return busy


def blocked_ranges(db: Session, technician_id: str, day_start_utc: datetime, day_end_utc: datetime) -> list[tuple[datetime, datetime]]:
    rows = db.execute(
        select(TechnicianBlock.start_utc, TechnicianBlock.end_utc).where(
            TechnicianBlock.technician_id == technician_id,
            TechnicianBlock.start_utc < day_end_utc,
            TechnicianBlock.end_utc > day_start_utc,
        )
    ).all()
    return [(start, end) for start, end in rows]


def find_candidates(
    db: Session,
    settings: Settings,
    service: Service,
    day: date,
    *,
    after: str | None = None,
    before: str | None = None,
    exclude_booking_id: str | None = None,
) -> list[Candidate]:
    """Available, qualified, non-overlapping options for one business day."""
    after_hm = parse_hhmm(after)
    before_hm = parse_hhmm(before)
    technicians = db.execute(
        select(Technician).where(Technician.active.is_(True)).order_by(Technician.name)
    ).scalars().all()
    qualified = [t for t in technicians if service.required_skill in (t.skills or [])]
    if not qualified:
        return []

    duration = timedelta(minutes=service.duration_minutes)
    day_start = local_instant(day, 0, 0, settings.tz)
    day_end = day_start + timedelta(days=1)
    busy = technician_busy_map(db, [t.id for t in qualified], day_start, day_end)

    candidates: list[Candidate] = []
    earliest = after_hm or (8, 0)
    for tech in qualified:
        blocked = blocked_ranges(db, tech.id, day_start, day_end)
        cursor_day = day
        slot_local = local_instant(cursor_day, earliest[0], earliest[1], settings.tz)
        latest_local = local_instant(cursor_day, (before_hm or (20, 0))[0], (before_hm or (20, 0))[1], settings.tz)
        taken = busy.get(tech.id, set())
        while slot_local + duration <= latest_local + timedelta(minutes=1):
            end_local = slot_local + duration
            if not is_business_open(slot_local, end_local, settings.tz):
                slot_local += timedelta(minutes=SLOT_MINUTES)
                continue
            cells = slot_starts(slot_local, end_local)
            if any(cell in taken for cell in cells):
                slot_local += timedelta(minutes=SLOT_MINUTES)
                continue
            if any(slot_local < b_end and end_local > b_start for b_start, b_end in blocked):
                slot_local += timedelta(minutes=SLOT_MINUTES)
                continue
            candidates.append(Candidate(technician=tech, start_utc=slot_local, end_utc=end_local))
            slot_local += timedelta(minutes=SLOT_MINUTES)

    candidates.sort(key=lambda c: (c.start_utc, c.technician.name))
    return candidates


def is_window_free(db: Session, technician_id: str, start_utc: datetime, end_utc: datetime) -> bool:
    if claimed_cells(db, technician_id, start_utc, end_utc):
        return False
    for block_start, block_end in blocked_ranges(db, technician_id, start_utc, end_utc + timedelta(minutes=1)):
        if start_utc < block_end and end_utc > block_start:
            return False
    return True


def claim_cells(db: Session, technician_id: str, start_utc: datetime, end_utc: datetime, kind: str, owner_id: str) -> None:
    """Insert capacity cells. The partial unique index raises on a lost race.

    Idempotent for the *same* owner (a booking that already holds its cells is not
    a conflict with itself); any other owner occupying a cell is a real conflict.
    """
    starts = slot_starts(start_utc, end_utc)
    existing = db.execute(
        select(SlotBlock).where(
            SlotBlock.technician_id == technician_id,
            SlotBlock.active == 1,
            SlotBlock.slot_start_utc.in_(starts),
        )
    ).scalars().all()
    taken = {row.slot_start_utc for row in existing}
    for row in existing:
        if row.owner_kind != kind or row.owner_id != owner_id:
            raise Conflict(
                "SLOT_UNAVAILABLE", "That slot was just taken. Please choose another option."
            )
    for slot in starts:
        if slot in taken:
            continue
        db.add(
            SlotBlock(
                technician_id=technician_id,
                slot_start_utc=slot,
                owner_kind=kind,
                owner_id=owner_id,
                active=1,
            )
        )
    db.flush()


def release_cells(db: Session, kind: str, owner_id: str) -> int:
    rows = db.execute(
        select(SlotBlock).where(
            SlotBlock.owner_kind == kind, SlotBlock.owner_id == owner_id, SlotBlock.active == 1
        )
    ).scalars().all()
    for row in rows:
        row.active = 0
    return len(rows)


def expire_stale_holds(db: Session, now: datetime) -> int:
    """Reclaim capacity from holds past their TTL. Uses server time only."""
    stale = db.execute(
        select(Hold).where(Hold.status == HoldStatus.active.value, Hold.expires_at <= now)
    ).scalars().all()
    if not stale:
        return 0
    for hold in stale:
        hold.status = HoldStatus.expired.value
        release_cells(db, "hold", hold.id)
        booking = db.execute(select(Booking).where(Booking.hold_id == hold.id)).scalar_one_or_none()
        if booking is not None and booking.status in {
            BookingStatus.held.value,
            BookingStatus.awaiting_payment.value,
        }:
            booking.status = BookingStatus.expired.value
    db.flush()
    return len(stale)
