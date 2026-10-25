"""Mandatory evidence: object ownership, role separation, CSRF, and input hardening."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Booking, BookingStatus, TechnicianBlock, User


def _headers(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def _book_for(client, headers, message="washing machine tomorrow after 4 PM") -> dict:
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
    client.post(f"/api/simulated-checkout/{checkout['simulated_token']}/approve", headers=headers)
    client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    return checkout


def test_unauthenticated_requests_are_rejected(client):
    for path in ["/api/bookings", "/api/owner/timeline", "/api/owner/analytics"]:
        resp = client.get(path)
        assert resp.status_code == 401, path
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_one_customer_cannot_read_another_customers_booking(client, login):
    login("maya@example.com")
    headers = _headers(client)
    mine = _book_for(client, headers)
    client.post("/api/auth/logout", headers=headers)

    login("diego@example.com")
    other_headers = _headers(client)
    resp = client.get(f"/api/bookings/{mine['booking_id']}", headers=other_headers)
    assert resp.status_code == 404, "foreign objects must 404, not 403, to avoid enumeration"

    resp = client.get(f"/api/payments/{mine['attempt_id']}", headers=other_headers)
    assert resp.status_code == 404

    resp = client.post(f"/api/payments/{mine['attempt_id']}/capture", headers=other_headers)
    assert resp.status_code == 404

    resp = client.delete(f"/api/holds/{mine['booking_id']}", headers=other_headers)
    assert resp.status_code == 404

    listed = client.get("/api/bookings", headers=other_headers).json()
    assert mine["booking_id"] not in {b["id"] for b in listed}


def test_customer_listing_never_leaks_other_customers(client, login, db):
    login("maya@example.com")
    maya_headers = _headers(client)
    maya_ids = {b["id"] for b in client.get("/api/bookings", headers=maya_headers).json()}
    maya_user = db.execute(select(User).where(User.email == "maya@example.com")).scalar_one()
    for booking in db.execute(select(Booking).where(Booking.id.in_(maya_ids))).scalars():
        assert booking.customer_id == maya_user.id


def test_customer_cannot_use_owner_endpoints(client, login, db):
    login("maya@example.com")
    headers = _headers(client)

    for path in ["/api/owner/timeline", "/api/owner/analytics", "/api/owner/bookings", "/api/owner/audit"]:
        resp = client.get(path, headers=headers)
        assert resp.status_code == 403, path
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    disruption = client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T14:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Sick leave",
        },
        headers=headers,
    )
    assert disruption.status_code == 403
    assert db.execute(select(TechnicianBlock)).scalars().first() is None


def test_owner_cannot_act_as_customer(client, login):
    login("owner@northline.example")
    headers = _headers(client)
    resp = client.post("/api/holds", json={
        "service_code": "washer-repair",
        "technician_id": "tech_ana",
        "start_utc": "2026-11-04T16:00:00-05:00",
    }, headers=headers)
    assert resp.status_code == 403
    resp = client.post("/api/assistant/message", json={"message": "hi"}, headers=headers)
    assert resp.status_code == 403


def test_csrf_header_is_required_for_writes(client, login):
    login("maya@example.com")
    resp = client.post("/api/assistant/message", json={"message": "washing machine tomorrow"})
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["error"]["message"]

    # A mismatched token is also rejected.
    resp = client.post(
        "/api/assistant/message",
        json={"message": "washing machine tomorrow"},
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )
    assert resp.status_code == 403


def test_cross_origin_write_is_rejected(client, login):
    login("maya@example.com")
    resp = client.post(
        "/api/assistant/message",
        json={"message": "washing machine tomorrow"},
        headers={**_headers(client), "Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


def test_unknown_email_cannot_log_in(client):
    resp = client.post("/api/auth/login", json={"email": "attacker@example.com"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_request_schema_rejects_unknown_and_oversized_fields(client, login):
    login("maya@example.com")
    headers = _headers(client)
    resp = client.post(
        "/api/holds",
        json={
            "service_code": "washer-repair",
            "technician_id": "tech_ana",
            "start_utc": "2026-11-04T16:00:00-05:00",
            "price_cents": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 422, "clients may not supply price"

    resp = client.post(
        "/api/assistant/message",
        json={"message": "x" * 5000},
        headers=headers,
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/holds",
        json={
            "service_code": "washer-repair",
            "technician_id": "tech_ana",
            "start_utc": "not-a-date",
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_naive_datetime_is_rejected(client, login):
    login("maya@example.com")
    resp = client.post(
        "/api/holds",
        json={
            "service_code": "washer-repair",
            "technician_id": "tech_ana",
            "start_utc": "2026-11-04T16:00:00",
        },
        headers=_headers(client),
    )
    assert resp.status_code == 422


def test_logout_invalidates_the_session(client, login):
    login("maya@example.com")
    headers = _headers(client)
    assert client.get("/api/bookings", headers=headers).status_code == 200
    client.post("/api/auth/logout", headers=headers)
    client.cookies.clear()
    assert client.get("/api/bookings", headers=headers).status_code == 401


def test_unqualified_technician_cannot_take_the_job(client, login):
    login("maya@example.com")
    # Cy is kitchen+laundry; force a dishwasher job onto a laundry-only tech.
    resp = client.post(
        "/api/holds",
        json={
            "service_code": "dishwasher-install",
            "technician_id": "tech_ben",
            "start_utc": "2026-11-04T09:00:00-05:00",
        },
        headers=_headers(client),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "TECHNICIAN_NOT_QUALIFIED"


def test_outside_business_hours_is_rejected(client, login):
    login("maya@example.com")
    resp = client.post(
        "/api/holds",
        json={
            "service_code": "washer-repair",
            "technician_id": "tech_ana",
            "start_utc": "2026-11-04T21:00:00-05:00",
        },
        headers=_headers(client),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "OUTSIDE_BUSINESS_HOURS"
