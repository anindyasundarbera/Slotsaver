from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SLOT_MINUTES = 30

# Business opening hours per weekday (Mon=0). Closed Sunday.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    0: (time(8, 0), time(18, 0)),
    1: (time(8, 0), time(18, 0)),
    2: (time(8, 0), time(18, 0)),
    3: (time(8, 0), time(18, 0)),
    4: (time(8, 0), time(18, 0)),
    5: (time(9, 0), time(14, 0)),
}


def to_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def local_instant(day: date, hh: int, mm: int, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=tz).astimezone(timezone.utc)


def is_slot_aligned(dt: datetime) -> bool:
    """True when `dt` sits exactly on a 30-minute cell boundary."""
    return dt.minute in (0, SLOT_MINUTES) and dt.second == 0 and dt.microsecond == 0


def assert_slot_aligned(dt: datetime, label: str = "start") -> None:
    if not is_slot_aligned(dt):
        raise ValueError(f"{label} must be aligned to a 30-minute boundary")


def slot_starts(start_utc: datetime, end_utc: datetime) -> list[datetime]:
    """Every 30-minute capacity cell covered by [start, end)."""
    if end_utc <= start_utc:
        raise ValueError("end must be after start")
    if not is_slot_aligned(start_utc):
        raise ValueError("start must align to 30-minute cells")
    total = int((end_utc - start_utc).total_seconds())
    if total % (SLOT_MINUTES * 60) != 0:
        raise ValueError("reservation must align to 30-minute cells")
    return [start_utc + timedelta(minutes=SLOT_MINUTES * i) for i in range(total // (SLOT_MINUTES * 60))]


def is_business_open(start_utc: datetime, end_utc: datetime, tz: ZoneInfo) -> bool:
    local_start = start_utc.astimezone(tz)
    local_end = end_utc.astimezone(tz)
    if local_start.date() != local_end.date():
        return False
    hours = OPENING_HOURS.get(local_start.weekday())
    if hours is None:
        return False
    open_at, close_at = hours
    return local_start.time() >= open_at and local_end.time() <= close_at


def business_days(tz: ZoneInfo, start_day: date, days: int) -> list[date]:
    out: list[date] = []
    cursor = start_day
    while len(out) < days:
        if cursor.weekday() in OPENING_HOURS:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def next_business_day(tz: ZoneInfo, after: date) -> date:
    cursor = after + timedelta(days=1)
    while cursor.weekday() not in OPENING_HOURS:
        cursor += timedelta(days=1)
    return cursor


def format_local(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%a %d %b %Y, %-I:%M %p") if dt.tzinfo else str(dt)


def tz_label(tz: ZoneInfo, at: datetime) -> str:
    offset = at.astimezone(tz).utcoffset() or timedelta(0)
    hours = int(offset.total_seconds() // 3600)
    return f"UTC{hours:+d}"
