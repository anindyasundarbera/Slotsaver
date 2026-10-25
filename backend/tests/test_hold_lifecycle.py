"""Cancelled checkout, hold expiry, and concurrency."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import utcnow
from app.errors import Conflict
from app.models import Booking, BookingStatus, Hold, HoldStatus, SlotBlock, User
from app.services import availability, bookings as booking_service
from app.services.payments import SimulatedProvider


def _option(client, headers):
    reply = client.post(
        "/api/assistant/message",
        json={"message": "washing machine tomorrow after 4 PM"},
        headers=headers,
    ).json()
    return reply["options"]


def test_cancelled_checkout_does_not_confirm_and_frees_capacity(client, login, db):
    login("maya@example.com")
    headers = {"X-CSRF-Token": client.cookies.get("ss_csrf")}
    option = _option(client, headers)[0]

    hold = client.post(
        "/api/holds",
        json={
            "service_code": option["service_code"],
            "technician_id": option["technician_id"],
            "start_utc": option["start_utc"],
        },
        headers=headers,
    ).json()
    checkout = client.post(f"/api/holds/{hold['id']}/checkout", headers=headers).json()
    client.post(f"/api/simulated-checkout/{checkout['simulated_token']}/decline", headers=headers)
    cancelled = client.post(f"/api/payments/{checkout['attempt_id']}/cancel", headers=headers)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["booking_status"] == "cancelled"

    booking = client.get(f"/api/bookings/{checkout['booking_id']}", headers=headers).json()
    assert booking["status"] == "cancelled"
    assert booking["confirmed_at"] is None

    # Capacity is reclaimable: the same slot can be held again.
    again = client.post(
        "/api/holds",
        json={
            "service_code": option["service_code"],
            "technician_id": option["technician_id"],
            "start_utc": option["start_utc"],
        },
        headers=headers,
    )
    assert again.status_code == 201, again.text


def test_expired_hold_releases_capacity_and_cannot_be_confirmed(client, login, db, settings):
    login("maya@example.com")
    headers = {"X-CSRF-Token": client.cookies.get("ss_csrf")}
    option = _option(client, headers)[0]
    hold_resp = client.post(
        "/api/holds",
        json={
            "service_code": option["service_code"],
            "technician_id": option["technician_id"],
            "start_utc": option["start_utc"],
        },
        headers=headers,
    )
    hold_id = hold_resp.json()["id"]

    # Move the hold into the past using the server clock, not the wall clock.
    hold = db.get(Hold, hold_id)
    hold.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    capacity = db.execute(
        select(SlotBlock).where(SlotBlock.owner_kind == "hold", SlotBlock.owner_id == hold_id)
    ).scalars().all()
    assert capacity and all(b.active == 1 for b in capacity)

    checkout = client.post(f"/api/holds/{hold_id}/checkout", headers=headers)
    assert checkout.status_code == 409
    assert checkout.json()["error"]["code"] == "HOLD_EXPIRED"

    db.expire_all()
    assert db.get(Hold, hold_id).status == HoldStatus.expired.value
    released = db.execute(
        select(SlotBlock).where(SlotBlock.owner_kind == "hold", SlotBlock.owner_id == hold_id)
    ).scalars().all()
    assert all(b.active == 0 for b in released)

    booking = db.execute(select(Booking).where(Booking.hold_id == hold_id)).scalar_one()
    assert booking.status == BookingStatus.expired.value


def test_two_customers_racing_for_one_slot_exactly_one_wins(client, login, db, settings):
    """Direct service-level race: the DB constraint, not a SELECT-then-INSERT, decides."""
    maya = db.execute(select(User).where(User.email == "maya@example.com")).scalar_one()
    diego = db.execute(select(User).where(User.email == "diego@example.com")).scalar_one()

    reply = client.post(
        "/api/auth/login", json={"email": "maya@example.com"}
    )
    headers = {"X-CSRF-Token": client.cookies.get("ss_csrf")}
    option = _option(client, headers)[0]
    client.post("/api/auth/logout", headers=headers)

    start = __import__("datetime").datetime.fromisoformat(option["start_utc"])

    first, _ = booking_service.create_hold(
        db,
        settings,
        customer=maya,
        service_code=option["service_code"],
        technician_id=option["technician_id"],
        start_utc=start,
    )
    db.commit()

    with pytest.raises(Conflict) as excinfo:
        booking_service.create_hold(
            db,
            settings,
            customer=diego,
            service_code=option["service_code"],
            technician_id=option["technician_id"],
            start_utc=start,
        )
    db.rollback()
    assert excinfo.value.code == "SLOT_UNAVAILABLE"

    active = db.execute(
        select(SlotBlock).where(
            SlotBlock.technician_id == option["technician_id"], SlotBlock.active == 1
        )
    ).scalars().all()
    owners = {b.owner_id for b in active}
    assert first.id in owners


def test_overlapping_but_offset_slot_is_rejected(client, login, db, settings):
    """A 90-minute job starting 30 minutes later overlaps the first hold's cells."""
    maya = db.execute(select(User).where(User.email == "maya@example.com")).scalar_one()
    login("maya@example.com")
    headers = {"X-CSRF-Token": client.cookies.get("ss_csrf")}
    options = _option(client, headers)
    base = options[0]
    start = __import__("datetime").datetime.fromisoformat(base["start_utc"])

    booking_service.create_hold(
        db,
        settings,
        customer=maya,
        service_code=base["service_code"],
        technician_id=base["technician_id"],
        start_utc=start,
    )
    db.commit()

    with pytest.raises(Conflict):
        booking_service.create_hold(
            db,
            settings,
            customer=maya,
            service_code=base["service_code"],
            technician_id=base["technician_id"],
            start_utc=start + timedelta(minutes=30),
        )
    db.rollback()
