from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .models import (
    AttemptStatus,
    Booking,
    BookingStatus,
    DemoClock,
    Hold,
    HoldStatus,
    PaymentAttempt,
    Service,
    SlotBlock,
    Technician,
    User,
)
from .timeutil import OPENING_HOURS, local_instant, slot_starts

log = logging.getLogger("slotsaver.seed")

DEMO_USERS = [
    ("maya@example.com", "Maya Chen", "customer"),
    ("diego@example.com", "Diego Alvarez", "customer"),
    ("owner@northline.example", "Priya Raman", "owner"),
]

SERVICES = [
    {
        "code": "washer-repair",
        "name": "Washing machine repair",
        "duration_minutes": 90,
        "price_cents": 7500,
        "required_skill": "laundry",
        "description": "Diagnose and repair a washing machine. Parts quoted separately.",
    },
    {
        "code": "dryer-repair",
        "name": "Dryer repair",
        "duration_minutes": 60,
        "price_cents": 6500,
        "required_skill": "laundry",
        "description": "Diagnose and repair a dryer, including vent basics.",
    },
    {
        "code": "dishwasher-install",
        "name": "Dishwasher installation",
        "duration_minutes": 120,
        "price_cents": 12000,
        "required_skill": "kitchen",
        "description": "Install a freestanding or built-in dishwasher, including a leak check.",
    },
]

TECHNICIANS = [
    {
        "id": "tech_ana",
        "name": "Ana Ortiz",
        "initials": "AO",
        "skills": ["laundry", "kitchen"],
        "color": "#2563eb",
    },
    {
        "id": "tech_ben",
        "name": "Ben Kowalski",
        "initials": "BK",
        "skills": ["laundry"],
        "color": "#7c3aed",
    },
    {
        "id": "tech_cy",
        "name": "Cy Nguyen",
        "initials": "CN",
        "skills": ["kitchen", "laundry"],
        "color": "#0d9488",
    },
]


def _seed_booking(
    db: Session,
    settings: Settings,
    *,
    customer: User,
    service: Service,
    technician: Technician,
    start_utc: datetime,
    status: str,
    reference: str,
    notes: str = "",
    price_cents: int | None = None,
    needs_attention: bool = False,
    exception_reason: str = "",
    payment_status: str | None = None,
) -> Booking:
    end_utc = start_utc + timedelta(minutes=service.duration_minutes)
    price = price_cents if price_cents is not None else service.price_cents

    hold = Hold(
        customer_id=customer.id,
        technician_id=technician.id,
        service_id=service.id,
        start_utc=start_utc,
        end_utc=end_utc,
        price_cents=price,
        currency=service.currency,
        status=HoldStatus.consumed.value
        if status in {BookingStatus.confirmed.value, BookingStatus.needs_reassignment.value}
        else HoldStatus.active.value,
        created_at=utcnow() - timedelta(days=2),
        expires_at=utcnow() + timedelta(minutes=settings.hold_ttl_minutes),
    )
    db.add(hold)
    db.flush()

    booking = Booking(
        reference=reference,
        customer_id=customer.id,
        technician_id=technician.id,
        service_id=service.id,
        hold_id=hold.id,
        start_utc=start_utc,
        end_utc=end_utc,
        price_cents=price,
        currency=service.currency,
        status=status,
        notes=notes,
        needs_attention=needs_attention,
        exception_reason=exception_reason,
        created_at=utcnow() - timedelta(days=2),
        confirmed_at=utcnow() - timedelta(days=2)
        if status in {BookingStatus.confirmed.value, BookingStatus.needs_reassignment.value}
        else None,
    )
    db.add(booking)
    db.flush()

    if status in {
        BookingStatus.confirmed.value,
        BookingStatus.needs_reassignment.value,
        BookingStatus.payment_exception.value,
    }:
        for slot in slot_starts(start_utc, end_utc):
            db.add(
                SlotBlock(
                    technician_id=technician.id,
                    slot_start_utc=slot,
                    owner_kind="booking",
                    owner_id=booking.id,
                    active=1,
                )
            )
        attempt = PaymentAttempt(
            booking_id=booking.id,
            hold_id=hold.id,
            customer_id=customer.id,
            idempotency_key=f"seed:{booking.reference}",
            provider="paypal",
            provider_mode=settings.paypal_mode,
            provider_order_id=f"SEEDORDER{booking.reference.replace('-', '')}",
            provider_capture_id=f"SEEDCAP{booking.reference.replace('-', '')}"
            if status != BookingStatus.payment_exception.value
            else None,
            expected_amount_cents=price,
            captured_amount_cents=price,
            currency=service.currency,
            status=payment_status
            or (
                AttemptStatus.reconciled_exception.value
                if status == BookingStatus.payment_exception.value
                else AttemptStatus.reconciled_ok.value
            ),
            raw_status="COMPLETED",
            captured_at=utcnow() - timedelta(days=2),
            failure_reason=exception_reason if status == BookingStatus.payment_exception.value else "",
        )
        db.add(attempt)
        db.flush()
    return booking


def seed_database(db: Session, settings: Settings, *, demo_date: date | None = None) -> dict:
    """Deterministic reset of the synthetic demo dataset.

    Uses metadata dependency order so foreign keys are respected; safe to call
    repeatedly (the reset endpoint and the test fixtures both rely on that).
    """
    from .db import Base

    ordered = list(reversed(Base.metadata.sorted_tables))
    for table in ordered:
        db.execute(table.delete())
    db.flush()

    day = demo_date or settings.demo_date
    db.add(DemoClock(id=1, demo_date=day.isoformat(), updated_at=utcnow()))

    users: dict[str, User] = {}
    for email, name, role in DEMO_USERS:
        user = User(email=email, display_name=name, role=role)
        db.add(user)
        users[email] = user
    db.flush()

    services: dict[str, Service] = {}
    for spec in SERVICES:
        service = Service(**spec)
        db.add(service)
        services[spec["code"]] = service
    db.flush()

    techs: dict[str, Technician] = {}
    for spec in TECHNICIANS:
        tech = Technician(**spec)
        db.add(tech)
        techs[spec["id"]] = tech
    db.flush()

    maya = users["maya@example.com"]
    diego = users["diego@example.com"]
    washer = services["washer-repair"]
    dryer = services["dryer-repair"]
    dishwasher = services["dishwasher-install"]

    today = day

    def at(d: date, hh: int, mm: int = 0) -> datetime:
        return local_instant(d, hh, mm, settings.tz)

    def shift_business(d: date, n: int) -> date:
        cursor = d
        step = 1 if n > 0 else -1
        remaining = abs(n)
        while remaining:
            cursor += timedelta(days=step)
            if cursor.weekday() in OPENING_HOURS:
                remaining -= 1
        return cursor

    tomorrow = shift_business(today, 1)
    day_after = shift_business(today, 2)
    history = [shift_business(today, -k) for k in (3, 2, 1)]

    ana, ben, cy = techs["tech_ana"], techs["tech_ben"], techs["tech_cy"]
    bookings: list[Booking] = []

    # --- historical confirmed revenue
    history_specs = [
        (history[0], 9, 0, ana, washer, maya, "SA-H1A2B3", 7500),
        (history[0], 13, 0, ben, dryer, diego, "SA-H2C4D5", 6500),
        (history[1], 10, 0, cy, dishwasher, maya, "SA-H3E6F7", 12000),
        (history[1], 15, 0, ana, washer, diego, "SA-H4G8H9", 7500),
        (history[2], 11, 0, ben, dryer, maya, "SA-H5J1K2", 6500),
        (history[2], 14, 0, cy, dishwasher, diego, "SA-H6L3M4", 12000),
    ]
    for d, hh, mm, tech, service, customer, ref, price in history_specs:
        bookings.append(
            _seed_booking(
                db, settings, customer=customer, service=service, technician=tech,
                start_utc=at(d, hh, mm), status=BookingStatus.confirmed.value,
                reference=ref, price_cents=price, notes="Historic completed job",
            )
        )

    # --- demo day schedule (the timeline the presenter shows)
    bookings.append(_seed_booking(
        db, settings, customer=diego, service=dryer, technician=ben,
        start_utc=at(today, 9, 0), status=BookingStatus.confirmed.value,
        reference="SA-T1N5P6", notes="Dryer not heating",
    ))
    bookings.append(_seed_booking(
        db, settings, customer=maya, service=washer, technician=ana,
        start_utc=at(today, 11, 0), status=BookingStatus.confirmed.value,
        reference="SA-T2Q7R8", notes="Front loader leaking during spin",
    ))
    bookings.append(_seed_booking(
        db, settings, customer=maya, service=dryer, technician=ben,
        start_utc=at(today, 12, 30), status=BookingStatus.confirmed.value,
        reference="SA-T4U2V3", notes="Lint trap assembly replacement",
    ))
    bookings.append(_seed_booking(
        db, settings, customer=diego, service=dishwasher, technician=cy,
        start_utc=at(today, 16, 0), status=BookingStatus.confirmed.value,
        reference="SA-T3S9T1", notes="Cabinet cut-out already done",
    ))

    # Another customer's live hold: proves cross-customer isolation without leaking detail.
    cross_hold_start = at(today, 14, 0)
    cross_hold = Hold(
        customer_id=diego.id, technician_id=ana.id, service_id=washer.id,
        start_utc=cross_hold_start,
        end_utc=cross_hold_start + timedelta(minutes=washer.duration_minutes),
        price_cents=washer.price_cents, currency="USD",
        status=HoldStatus.active.value, created_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=settings.hold_ttl_minutes),
    )
    db.add(cross_hold)
    db.flush()
    for slot in slot_starts(cross_hold.start_utc, cross_hold.end_utc):
        db.add(SlotBlock(
            technician_id=ana.id, slot_start_utc=slot,
            owner_kind="hold", owner_id=cross_hold.id, active=1,
        ))
    db.flush()

    # --- tomorrow: Cy is busy at 16:00, so a 16:00 laundry request yields exactly
    #     two qualified options (Ana and Ben) — the demo's "two validated options".
    bookings.append(_seed_booking(
        db, settings, customer=diego, service=dishwasher, technician=cy,
        start_utc=at(tomorrow, 16, 0), status=BookingStatus.confirmed.value,
        reference="SA-M1N2P3", notes="Dishwasher install, second unit",
    ))
    bookings.append(_seed_booking(
        db, settings, customer=maya, service=dryer, technician=ben,
        start_utc=at(tomorrow, 10, 0), status=BookingStatus.confirmed.value,
        reference="SA-M4Q5R6", notes="Dryer belt replacement",
    ))

    # --- day after tomorrow: disruption target + an unresolved payment exception
    disruption_booking = _seed_booking(
        db, settings, customer=maya, service=washer, technician=ana,
        start_utc=at(day_after, 14, 0), status=BookingStatus.confirmed.value,
        reference="SA-D4E5F6", notes="Second visit for a persistent leak",
    )
    bookings.append(disruption_booking)
    bookings.append(_seed_booking(
        db, settings, customer=diego, service=dryer, technician=cy,
        start_utc=at(day_after, 10, 0), status=BookingStatus.payment_exception.value,
        reference="SA-X1Y2Z3", notes="Customer paid, slot was lost during capture",
        needs_attention=True, exception_reason="CAPTURED_AFTER_HOLD_EXPIRED",
    ))

    db.add(
        Booking(
            reference="SA-CANCELLED",
            customer_id=diego.id,
            technician_id=ana.id,
            service_id=washer.id,
            hold_id=None,
            start_utc=at(shift_business(today, 3), 10, 0),
            end_utc=at(shift_business(today, 3), 11, 30),
            price_cents=washer.price_cents,
            currency="USD",
            status=BookingStatus.cancelled.value,
            notes="Cancelled by customer",
            cancelled_at=utcnow() - timedelta(days=1),
        )
    )
    db.flush()

    return {
        "demo_date": day.isoformat(),
        "tomorrow": tomorrow.isoformat(),
        "day_after": day_after.isoformat(),
        "disruption_booking": disruption_booking.reference,
        "users": {email: user.id for email, user in users.items()},
        "services": {code: service.id for code, service in services.items()},
        "technicians": {tid: tech.id for tid, tech in techs.items()},
        "bookings": [b.reference for b in bookings],
        "history_days": [d.isoformat() for d in history],
    }
