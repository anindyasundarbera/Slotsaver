"""Regressions found during self-audit and independent review."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import utcnow
from app.errors import Conflict
from app.models import Booking, BookingStatus, Hold, PaymentAttempt, SlotBlock, User
from app.services import availability, bookings as booking_service


def _headers(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def _hold_and_checkout(client, headers, message="dryer repair tomorrow after 9 AM"):
    reply = client.post("/api/assistant/message", json={"message": message}, headers=headers).json()
    option = reply["options"][0]
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
    return hold, checkout


def test_checkout_retry_after_failed_attempt_creates_a_new_attempt(client, login, db):
    """Bug: a closed attempt collided on the idempotency key and returned 500."""
    login("maya@example.com")
    headers = _headers(client)
    hold, checkout = _hold_and_checkout(client, headers)

    attempt = db.get(PaymentAttempt, checkout["attempt_id"])
    attempt.status = "failed"
    attempt.failure_reason = "PROVIDER_TIMEOUT"
    db.commit()

    retry = client.post(f"/api/holds/{hold['id']}/checkout", headers=headers)
    assert retry.status_code == 201, retry.text
    assert retry.json()["attempt_id"] != checkout["attempt_id"]

    db.expire_all()
    attempts = db.execute(
        select(PaymentAttempt).where(PaymentAttempt.hold_id == hold["id"])
    ).scalars().all()
    assert len(attempts) == 2
    assert {a.attempt_no for a in attempts} == {1, 2}
    assert len({a.idempotency_key for a in attempts}) == 2


def test_repeated_checkout_with_open_attempt_is_still_idempotent(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    hold, checkout = _hold_and_checkout(client, headers)
    again = client.post(f"/api/holds/{hold['id']}/checkout", headers=headers)
    assert again.status_code == 201
    assert again.json()["attempt_id"] == checkout["attempt_id"]


def test_force_confirm_refuses_when_the_slot_was_taken(client, login, db):
    """Bug: force-confirm could double-book a technician."""
    login("owner@northline.example")
    headers = _headers(client)

    exception_booking = db.execute(
        select(Booking).where(Booking.reference == "SA-X1Y2Z3")
    ).scalar_one()
    db.expire_all()

    # Simulate another customer winning that window in the meantime: release the
    # exception's own cells, then claim every cell for a different owner.
    from app.timeutil import slot_starts

    availability.release_cells(db, "booking", exception_booking.id)
    db.flush()
    for slot in slot_starts(exception_booking.start_utc, exception_booking.end_utc):
        db.add(
            SlotBlock(
                technician_id=exception_booking.technician_id,
                slot_start_utc=slot,
                owner_kind="booking",
                owner_id="bkg_someone_else",
                active=1,
            )
        )
    db.commit()

    resp = client.post(
        f"/api/owner/bookings/{exception_booking.id}/resolve-exception",
        json={"resolution": "confirmed_manually", "note": "Owner override"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SLOT_UNAVAILABLE"
    db.expire_all()
    assert db.get(Booking, exception_booking.id).status == BookingStatus.payment_exception.value


def test_force_confirm_succeeds_and_claims_capacity_when_free(client, login, db):
    login("owner@northline.example")
    headers = _headers(client)
    exception_booking = db.execute(
        select(Booking).where(Booking.reference == "SA-X1Y2Z3")
    ).scalar_one()

    resp = client.post(
        f"/api/owner/bookings/{exception_booking.id}/resolve-exception",
        json={"resolution": "confirmed_manually", "note": "Verified transfer"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"

    db.expire_all()
    owned = db.execute(
        select(SlotBlock).where(
            SlotBlock.owner_kind == "booking",
            SlotBlock.owner_id == exception_booking.id,
            SlotBlock.active == 1,
        )
    ).scalars().all()
    assert owned, "a force-confirmed booking must own its capacity cells"


def test_cancel_path_releases_capacity_for_an_exception(client, login, db):
    login("owner@northline.example")
    headers = _headers(client)
    exception_booking = db.execute(
        select(Booking).where(Booking.reference == "SA-X1Y2Z3")
    ).scalar_one()
    resp = client.post(
        f"/api/owner/bookings/{exception_booking.id}/resolve-exception",
        json={"resolution": "cancelled", "note": "Refunded manually"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    db.expire_all()
    assert db.get(Booking, exception_booking.id).cancelled_at is not None


def test_concurrent_claims_survive_a_rollback_without_dangling_cells(db, settings):
    """A losing racer must not leave half-claimed capacity behind."""
    maya = db.execute(select(User).where(User.email == "maya@example.com")).scalar_one()
    diego = db.execute(select(User).where(User.email == "diego@example.com")).scalar_one()
    # Find a genuinely free technician + 90-minute window so the first claim wins.
    from app.models import Service, Technician

    service = db.execute(
        select(Service).where(Service.code == "washer-repair")
    ).scalar_one()
    duration = timedelta(minutes=service.duration_minutes)
    start = None
    technician = None
    for tech in db.execute(select(Technician)).scalars().all():
        if service.required_skill not in (tech.skills or []):
            continue
        for candidate in availability.find_candidates(
            db, settings, service, settings.demo_date
        ):
            if candidate.technician.id == tech.id:
                start, technician = candidate.start_utc, tech.id
                break
        if start is not None:
            break
    assert start is not None and technician is not None, "seed must leave a free laundry slot"

    first, _ = booking_service.create_hold(
        db, settings, customer=maya, service_code="washer-repair",
        technician_id=technician, start_utc=start,
    )
    db.commit()

    with pytest.raises(Conflict):
        booking_service.create_hold(
            db, settings, customer=diego, service_code="washer-repair",
            technician_id=technician, start_utc=start,
        )
    db.rollback()

    active = db.execute(
        select(SlotBlock).where(
            SlotBlock.technician_id == technician,
            SlotBlock.slot_start_utc == start,
            SlotBlock.active == 1,
        )
    ).scalars().all()
    assert len(active) == 1, "exactly one winner must own this cell"
    assert active[0].owner_id == first.id
