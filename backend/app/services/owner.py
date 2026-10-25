from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..models import (
    AttemptStatus,
    Booking,
    BookingStatus,
    Hold,
    HoldStatus,
    PaymentAttempt,
    Technician,
    TechnicianBlock,
)
from ..schemas import (
    AnalyticsBucket,
    AnalyticsOut,
    AnalyticsRow,
    TechnicianOut,
    TimelineEvent,
    TimelineOut,
)
from ..timeutil import local_instant, tz_label
from .bookings import STATUS_LABELS
from .serializers import local_pair

REVENUE_STATUSES = {BookingStatus.confirmed.value, BookingStatus.needs_reassignment.value}
EXCEPTION_STATUSES = {BookingStatus.payment_exception.value}


def timeline(db: Session, settings: Settings, day: date) -> TimelineOut:
    availability_expire(db, settings, day)
    day_start = local_instant(day, 0, 0, settings.tz)
    day_end = day_start + timedelta(days=1)

    technicians = db.execute(
        select(Technician).where(Technician.active.is_(True)).order_by(Technician.name)
    ).scalars().all()

    bookings = db.execute(
        select(Booking).where(
            Booking.start_utc < day_end,
            Booking.end_utc > day_start,
            Booking.status.in_(
                [
                    BookingStatus.held.value,
                    BookingStatus.awaiting_payment.value,
                    BookingStatus.confirmed.value,
                    BookingStatus.needs_reassignment.value,
                    BookingStatus.payment_exception.value,
                ]
            ),
        ).order_by(Booking.start_utc)
    ).scalars().all()

    holds = db.execute(
        select(Hold).where(
            Hold.status == HoldStatus.active.value,
            Hold.start_utc < day_end,
            Hold.end_utc > day_start,
        ).order_by(Hold.start_utc)
    ).scalars().all()

    blocks = db.execute(
        select(TechnicianBlock).where(
            TechnicianBlock.start_utc < day_end,
            TechnicianBlock.end_utc > day_start,
        ).order_by(TechnicianBlock.start_utc)
    ).scalars().all()

    colors = {
        BookingStatus.held.value: "#f59e0b",
        BookingStatus.awaiting_payment.value: "#f97316",
        BookingStatus.confirmed.value: "#16a34a",
        BookingStatus.needs_reassignment.value: "#dc2626",
        BookingStatus.payment_exception.value: "#9333ea",
    }

    events: list[TimelineEvent] = []
    hold_booking_ids = {h.id for h in holds}
    for booking in bookings:
        if booking.hold_id in hold_booking_ids:
            continue  # a held booking is rendered once, from its hold
        events.append(
            TimelineEvent(
                id=booking.id,
                kind="booking",
                technician_id=booking.technician_id,
                title=f"{booking.service.name} · {booking.reference}",
                start_utc=booking.start_utc,
                end_utc=booking.end_utc,
                status=booking.status,
                status_label=STATUS_LABELS.get(booking.status, booking.status),
                color=colors.get(booking.status, "#64748b"),
                customer_name=booking.customer.display_name,
                service_name=booking.service.name,
                reference=booking.reference,
                price_cents=booking.price_cents,
                needs_attention=booking.needs_attention,
            )
        )
    for hold in holds:
        events.append(
            TimelineEvent(
                id=hold.id,
                kind="hold",
                technician_id=hold.technician_id,
                title=f"Held · {hold.service.name}",
                start_utc=hold.start_utc,
                end_utc=hold.end_utc,
                status="held",
                status_label="Held (temporary)",
                color=colors[BookingStatus.held.value],
                service_name=hold.service.name,
                price_cents=hold.price_cents,
            )
        )
    for block in blocks:
        events.append(
            TimelineEvent(
                id=block.id,
                kind="block",
                technician_id=block.technician_id,
                title=block.reason or "Unavailable",
                start_utc=block.start_utc,
                end_utc=block.end_utc,
                status="unavailable",
                status_label="Unavailable",
                color="#475569",
            )
        )

    events.sort(key=lambda e: (e.start_utc, e.technician_id))
    return TimelineOut(
        day=day,
        timezone_label=tz_label(settings.tz, day_start),
        technicians=[
            TechnicianOut(
                id=t.id, name=t.name, initials=t.initials, skills=t.skills or [], color=t.color
            )
            for t in technicians
        ],
        events=events,
        generated_at=utcnow(),
    )


def availability_expire(db: Session, settings: Settings, day: date) -> None:
    from . import availability

    availability.expire_stale_holds(db, utcnow())


def analytics(db: Session, settings: Settings, date_from: date, date_to: date) -> AnalyticsOut:
    from . import availability

    availability.expire_stale_holds(db, utcnow())
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    span = (date_to - date_from).days
    if span > 120:
        raise ValueError("analytics range must be 120 days or less")

    range_start = local_instant(date_from, 0, 0, settings.tz)
    range_end = local_instant(date_to, 0, 0, settings.tz) + timedelta(days=1)

    bookings = db.execute(
        select(Booking).where(
            Booking.start_utc >= range_start,
            Booking.start_utc < range_end,
            Booking.status != BookingStatus.cancelled.value,
        ).order_by(Booking.start_utc)
    ).scalars().all()

    attempts = {
        a.booking_id: a
        for a in db.execute(
            select(PaymentAttempt).where(
                PaymentAttempt.booking_id.in_([b.id for b in bookings]) if bookings else False
            )
        ).scalars().all()
    }

    confirmed_count = 0
    confirmed_revenue = 0
    captured_all = 0
    exception_cents = 0
    exception_count = 0
    reassignment_count = 0

    by_service: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_technician: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_status: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    rows: list[AnalyticsRow] = []

    for booking in bookings:
        attempt = attempts.get(booking.id)
        captured = attempt.captured_amount_cents if attempt and attempt.captured_amount_cents else 0
        is_revenue = booking.status in REVENUE_STATUSES
        counted = is_revenue
        if is_revenue:
            confirmed_count += 1
            confirmed_revenue += booking.price_cents
        if captured:
            captured_all += captured
        if booking.status in EXCEPTION_STATUSES:
            exception_count += 1
            exception_cents += captured or booking.price_cents
        if booking.status == BookingStatus.needs_reassignment.value:
            reassignment_count += 1

        if is_revenue:
            by_service[booking.service.name][0] += 1
            by_service[booking.service.name][1] += booking.price_cents
            by_technician[booking.technician.name][0] += 1
            by_technician[booking.technician.name][1] += booking.price_cents
        by_status[STATUS_LABELS.get(booking.status, booking.status)][0] += 1
        by_status[STATUS_LABELS.get(booking.status, booking.status)][1] += (
            booking.price_cents if is_revenue else 0
        )

        start_local, _, _ = local_pair(booking.start_utc, booking.end_utc, settings)
        rows.append(
            AnalyticsRow(
                booking_id=booking.id,
                reference=booking.reference,
                status=booking.status,
                status_label=STATUS_LABELS.get(booking.status, booking.status),
                service_name=booking.service.name,
                technician_name=booking.technician.name,
                customer_name=booking.customer.display_name,
                day=booking.start_utc.astimezone(settings.tz).date(),
                start_local=start_local,
                price_cents=booking.price_cents,
                currency=booking.currency,
                counted_as_revenue=counted,
                needs_attention=booking.needs_attention,
                exception_reason=booking.exception_reason,
            )
        )

    def buckets(source: dict[str, list[int]]) -> list[AnalyticsBucket]:
        return [
            AnalyticsBucket(key=key, label=key, booking_count=v[0], revenue_cents=v[1])
            for key, v in sorted(source.items(), key=lambda kv: (-kv[1][1], kv[0]))
        ]

    notes = [
        "Confirmed revenue counts confirmed and needs-reassignment bookings only; "
        "a pending reassignment has already been paid.",
        "Captured money includes every verified capture in range, including payments "
        "that landed on payment exceptions.",
    ]
    if exception_cents:
        notes.append(
            f"{exception_count} payment exception(s) worth {exception_cents} cents are "
            "excluded from confirmed revenue and require manual resolution."
        )

    return AnalyticsOut(
        date_from=date_from,
        date_to=date_to,
        currency=settings.currency,
        confirmed_count=confirmed_count,
        confirmed_revenue_cents=confirmed_revenue,
        captured_all_cents=captured_all,
        exception_cents=exception_cents,
        exception_count=exception_count,
        needs_reassignment_count=reassignment_count,
        by_service=buckets(by_service),
        by_technician=buckets(by_technician),
        by_status=buckets(by_status),
        rows=rows,
        notes=notes,
    )
