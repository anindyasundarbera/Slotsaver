"""Mandatory evidence: amount/currency tampering, forged webhooks, duplicates, capture-after-expiry."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta

from sqlalchemy import select

from app.db import utcnow
from app.models import (
    AttemptStatus,
    Booking,
    BookingStatus,
    Hold,
    PaymentAttempt,
    ProcessedPaymentEvent,
    SlotBlock,
)
from app.services import bookings as booking_service
from app.services.payments import SimulatedProvider

TEST_WEBHOOK_KEY = "test-only-hmac-key-not-a-real-secret"


def _headers(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def _to_approved_order(client, headers) -> dict:
    reply = client.post(
        "/api/assistant/message",
        json={"message": "washing machine tomorrow after 4 PM"},
        headers=headers,
    ).json()
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
    return checkout


def test_altered_amount_is_refused_and_flagged(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    checkout = _to_approved_order(client, headers)

    # Tamper with the expected amount the way a client-side price change would.
    attempt = db.get(PaymentAttempt, checkout["attempt_id"])
    attempt.expected_amount_cents = 1  # $0.01 expected vs $75.00 captured
    db.commit()

    capture = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    assert capture.status_code == 200
    body = capture.json()
    assert body["status"] == "reconciled_exception"
    assert body["failure_reason"] == "AMOUNT_MISMATCH"
    assert body["booking_status"] == "payment_exception"

    db.expire_all()
    booking = db.get(Booking, checkout["booking_id"])
    assert booking.status == BookingStatus.payment_exception.value
    assert booking.needs_attention is True
    assert db.get(PaymentAttempt, attempt.id).captured_amount_cents == 7500


def test_altered_currency_is_refused(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    checkout = _to_approved_order(client, headers)
    attempt = db.get(PaymentAttempt, checkout["attempt_id"])
    attempt.currency = "EUR"
    db.commit()
    capture = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    assert capture.json()["failure_reason"] == "CURRENCY_MISMATCH"
    assert capture.json()["booking_status"] == "payment_exception"


def test_foreign_order_id_cannot_be_captured(client, login, db):
    login("diego@example.com")
    headers = _headers(client)
    foreign = _to_approved_order(client, headers)

    client.post("/api/auth/logout", headers=headers)
    login("maya@example.com")
    headers = _headers(client)

    stolen = client.post(f"/api/payments/{foreign['attempt_id']}/capture", headers=headers)
    assert stolen.status_code == 404
    assert stolen.json()["error"]["code"] == "NOT_FOUND"

    db.expire_all()
    assert db.get(Booking, foreign["booking_id"]).status != BookingStatus.confirmed.value


def test_duplicate_capture_is_idempotent_and_charges_once(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    checkout = _to_approved_order(client, headers)

    first = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    second = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    third = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)

    assert first.status_code == second.status_code == third.status_code == 200
    assert {first.json()["status"], second.json()["status"], third.json()["status"]} == {
        "reconciled_ok"
    }
    assert second.json()["captured_amount_cents"] == 7500

    db.expire_all()
    attempts = db.execute(
        select(PaymentAttempt).where(PaymentAttempt.booking_id == checkout["booking_id"])
    ).scalars().all()
    assert len(attempts) == 1, "a duplicate capture must not create a second attempt"
    assert attempts[0].captured_amount_cents == 7500


def test_duplicate_checkout_returns_same_order(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    reply = client.post(
        "/api/assistant/message",
        json={"message": "dryer repair tomorrow after 9 AM"},
        headers=headers,
    ).json()
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
    first = client.post(f"/api/holds/{hold['id']}/checkout", headers=headers).json()
    second = client.post(f"/api/holds/{hold['id']}/checkout", headers=headers).json()
    assert first["attempt_id"] == second["attempt_id"]
    assert first["simulated_token"] == second["simulated_token"]


def test_capture_after_hold_expiry_produces_payment_exception(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    checkout = _to_approved_order(client, headers)

    # Expire the hold behind the customer's back, then capture.
    hold = db.get(Hold, db.get(PaymentAttempt, checkout["attempt_id"]).hold_id)
    hold.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    capture = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    assert capture.status_code == 200
    body = capture.json()
    assert body["status"] == "reconciled_exception"
    assert body["failure_reason"] == "CAPTURED_AFTER_HOLD_EXPIRED"
    assert body["booking_status"] == "payment_exception"
    # The money is recorded, never dropped.
    assert body["captured_amount_cents"] == 7500

    db.expire_all()
    booking = db.get(Booking, checkout["booking_id"])
    assert booking.status == BookingStatus.payment_exception.value
    assert booking.needs_attention is True
    assert "CAPTURED_AFTER_HOLD_EXPIRED" in booking.exception_reason


def test_forged_webhook_signature_is_rejected(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    checkout = _to_approved_order(client, headers)

    event = {
        "id": "WH-FORGED-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "SIMCAP-FAKE", "supplementary_data": {"related_ids": {"order_id": checkout["simulated_token"]}}},
    }
    resp = client.post(
        "/api/webhooks/paypal",
        content=json.dumps(event),
        headers={"Content-Type": "application/json", "paypal-transmission-sig": "deadbeef"},
    )
    assert resp.status_code == 401
    db.expire_all()
    assert db.get(Booking, checkout["booking_id"]).status != BookingStatus.confirmed.value
    assert db.get(ProcessedPaymentEvent, "WH-FORGED-1") is None


def _signed(event: dict) -> tuple[bytes, dict]:
    body = json.dumps(event).encode()
    sig = hmac.new(TEST_WEBHOOK_KEY.encode(), body, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json", "paypal-transmission-sig": sig}


def test_signed_webhook_confirms_and_duplicates_are_ignored(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    reply = client.post(
        "/api/assistant/message",
        json={"message": "dryer repair tomorrow after 9 AM"},
        headers=headers,
    ).json()
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

    # Shape mirrors a real PAYMENT.CAPTURE.COMPLETED resource.
    event = {
        "id": "WH-SIGNED-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "SIMCAP-ABC",
            "status": "COMPLETED",
            "amount": {"value": "65.00", "currency_code": "USD"},
            "custom_id": checkout["attempt_id"],
            "supplementary_data": {"related_ids": {"order_id": checkout["simulated_token"]}},
        },
    }
    body, hdrs = _signed(event)
    first = client.post("/api/webhooks/paypal", content=body, headers=hdrs)
    assert first.status_code == 200

    db.expire_all()
    assert db.get(Booking, checkout["booking_id"]).status == BookingStatus.confirmed.value

    # Replay the identical event: deduped, no second effect.
    second = client.post("/api/webhooks/paypal", content=body, headers=hdrs)
    assert second.status_code == 200
    db.expire_all()
    assert db.get(Booking, checkout["booking_id"]).status == BookingStatus.confirmed.value
    assert db.get(ProcessedPaymentEvent, "WH-SIGNED-1").note.startswith("applied")

    # A *new* event id for the same order must also not double-confirm or double-charge.
    replay = {**event, "id": "WH-SIGNED-2"}
    body2, hdrs2 = _signed(replay)
    third = client.post("/api/webhooks/paypal", content=body2, headers=hdrs2)
    assert third.status_code == 200
    db.expire_all()
    attempts = db.execute(
        select(PaymentAttempt).where(PaymentAttempt.booking_id == checkout["booking_id"])
    ).scalars().all()
    assert len(attempts) == 1
    assert attempts[0].captured_amount_cents == 6500


def test_webhook_for_unknown_order_is_ignored(client, login, db):
    login("maya@example.com")
    event = {
        "id": "WH-UNKNOWN-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "SIMCAP-NOPE",
            "supplementary_data": {"related_ids": {"order_id": "SIMORDER-DOES-NOT-EXIST"}},
        },
    }
    body, hdrs = _signed(event)
    resp = client.post("/api/webhooks/paypal", content=body, headers=hdrs)
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(ProcessedPaymentEvent, "WH-UNKNOWN-1").note == "no_matching_attempt"


def test_unapproved_order_cannot_be_captured(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
    reply = client.post(
        "/api/assistant/message",
        json={"message": "dryer repair tomorrow after 9 AM"},
        headers=headers,
    ).json()
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

    capture = client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    assert capture.status_code == 409
    assert capture.json()["error"]["code"] == "ORDER_NOT_APPROVED"
    db.expire_all()
    assert db.get(Booking, checkout["booking_id"]).status != BookingStatus.confirmed.value
