"""Mandatory evidence: conversational request -> options -> hold -> payment -> confirmation."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Booking, BookingStatus, PaymentAttempt

DEMO_REQUEST = (
    "I need washing-machine service tomorrow after 4 PM. "
    "My budget is $80, and it must finish before 6."
)


def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def test_health_and_config_are_public(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    cfg = client.get("/api/config").json()
    assert cfg["timezone"] == "America/New_York"
    assert cfg["currency"] == "USD"
    assert {u["role"] for u in cfg["demo_users"]} == {"customer", "owner"}


def test_conversational_request_returns_real_options(client, login):
    login("maya@example.com")
    resp = client.post("/api/assistant/message", json={"message": DEMO_REQUEST}, headers=_csrf(client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "scripted"
    assert body["tool_trace"], "the assistant must show real tool activity"
    assert body["tool_trace"][0]["tool"] == "search_availability"
    assert body["options"], "the seeded demo request must yield options"
    first = body["options"][0]
    # Constraints from the sentence are honoured: after 4 PM, finishes before 6 PM, <= $80.
    assert "4:00 PM" in first["start_local"] or "4:30 PM" in first["start_local"]
    assert first["price_cents"] <= 8000
    assert first["timezone_label"] == "UTC-5"
    for option in body["options"]:
        local_end = option["end_local"]
        hour = int(local_end.split(":")[0]) + (12 if "PM" in local_end else 0)
        assert hour <= 18


def test_full_hold_checkout_capture_confirms_booking(client, login, db):
    login("maya@example.com")
    headers = _csrf(client)
    reply = client.post("/api/assistant/message", json={"message": DEMO_REQUEST}, headers=headers).json()
    option = reply["options"][0]

    hold_resp = client.post(
        "/api/holds",
        json={
            "service_code": option["service_code"],
            "technician_id": option["technician_id"],
            "start_utc": option["start_utc"],
            "notes": "Front loader leaking",
        },
        headers=headers,
    )
    assert hold_resp.status_code == 201, hold_resp.text
    hold = hold_resp.json()
    assert hold["status"] == "active"
    assert hold["price_cents"] == option["price_cents"]
    assert hold["seconds_remaining"] > 0

    checkout = client.post(f"/api/holds/{hold['id']}/checkout", headers=headers)
    assert checkout.status_code == 201, checkout.text
    checkout_body = checkout.json()
    assert checkout_body["provider_mode"] == "simulated"
    assert checkout_body["amount_cents"] == hold["price_cents"]
    assert checkout_body["simulated_token"]

    approve = client.post(
        f"/api/simulated-checkout/{checkout_body['simulated_token']}/approve", headers=headers
    )
    assert approve.status_code == 200

    capture = client.post(f"/api/payments/{checkout_body['attempt_id']}/capture", headers=headers)
    assert capture.status_code == 200, capture.text
    assert capture.json()["status"] == "reconciled_ok"
    assert capture.json()["booking_status"] == "confirmed"

    booking = client.get(f"/api/bookings/{checkout_body['booking_id']}", headers=headers)
    assert booking.status_code == 200
    body = booking.json()
    assert body["status"] == "confirmed"
    assert body["reference"].startswith("SA-")
    assert body["confirmed_at"] is not None
    assert body["payment_status"] == "reconciled_ok"

    # Persisted, not just in-memory: re-read straight from the database.
    db.expire_all()
    stored = db.get(Booking, body["id"])
    assert stored.status == BookingStatus.confirmed.value
    attempt = db.execute(
        select(PaymentAttempt).where(PaymentAttempt.booking_id == stored.id)
    ).scalar_one()
    assert attempt.captured_amount_cents == hold["price_cents"]
    assert attempt.provider_capture_id


def test_confirmation_survives_client_refresh(client, login):
    login("maya@example.com")
    headers = _csrf(client)
    reply = client.post("/api/assistant/message", json={"message": DEMO_REQUEST}, headers=headers).json()
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
    client.post(f"/api/simulated-checkout/{checkout['simulated_token']}/approve", headers=headers)
    client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)

    # A "refresh" is just an authoritative re-read.
    listed = client.get("/api/bookings", headers=headers).json()
    match = [b for b in listed if b["id"] == checkout["booking_id"]]
    assert match and match[0]["status"] == "confirmed"
    assert match[0]["payment_status"] == "reconciled_ok"
