"""Mandatory evidence: restart and refresh preserve bookings, payments, and analytics."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Booking, BookingStatus, PaymentAttempt


def _headers(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def test_state_survives_app_restart(settings):
    """Two separate app instances over the same SQLite file see identical state."""
    from fastapi.testclient import TestClient

    from app.db import Base, dispose_engines, get_engine, make_session_factory
    from app.deps import reset_factory
    from app.main import create_app
    from app.seed import seed_database

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as db:
        seed_database(db, settings)
        db.commit()

    app_one = create_app(settings)
    with TestClient(app_one) as first:
        first.post("/api/auth/login", json={"email": "maya@example.com"})
        h = {"X-CSRF-Token": first.cookies.get("ss_csrf")}
        reply = first.post(
            "/api/assistant/message",
            json={"message": "washing machine tomorrow after 4 PM"},
            headers=h,
        ).json()
        option = reply["options"][0]
        hold = first.post(
            "/api/holds",
            json={
                "service_code": option["service_code"],
                "technician_id": option["technician_id"],
                "start_utc": option["start_utc"],
            },
            headers=h,
        ).json()
        checkout = first.post(f"/api/holds/{hold['id']}/checkout", headers=h).json()
        first.post(f"/api/simulated-checkout/{checkout['simulated_token']}/approve", headers=h)
        first.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=h)
        booking_id = checkout["booking_id"]

    # Tear the process-level caches down exactly as a restart would.
    dispose_engines()
    reset_factory()

    app_two = create_app(settings)
    with TestClient(app_two) as second:
        second.post("/api/auth/login", json={"email": "maya@example.com"})
        h2 = {"X-CSRF-Token": second.cookies.get("ss_csrf")}
        resp = second.get(f"/api/bookings/{booking_id}", headers=h2)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "confirmed"
        assert body["payment_status"] == "reconciled_ok"

    # And it is genuinely in the database, not reconstructed from memory.
    dispose_engines()
    reset_factory()
    engine = get_engine(settings.database_url)
    with make_session_factory(engine)() as db:
        stored = db.get(Booking, booking_id)
        assert stored.status == BookingStatus.confirmed.value
        attempt = db.execute(
            select(PaymentAttempt).where(PaymentAttempt.booking_id == booking_id)
        ).scalar_one()
        assert attempt.captured_amount_cents == stored.price_cents


def test_analytics_agree_with_seeded_and_mutated_records(client, login, db):
    login("maya@example.com")
    headers = _headers(client)
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
    client.post(f"/api/payments/{checkout['attempt_id']}/capture", headers=headers)
    client.post("/api/auth/logout", headers=headers)

    login("owner@northline.example")
    owner_headers = _headers(client)
    analytics = client.get("/api/owner/analytics", headers=owner_headers).json()

    # The headline number must equal the sum of the rows it claims to summarise.
    revenue_rows = [r for r in analytics["rows"] if r["counted_as_revenue"]]
    assert analytics["confirmed_count"] == len(revenue_rows)
    assert analytics["confirmed_revenue_cents"] == sum(r["price_cents"] for r in revenue_rows)

    by_service_total = sum(b["revenue_cents"] for b in analytics["by_service"])
    assert by_service_total == analytics["confirmed_revenue_cents"]
    by_tech_total = sum(b["revenue_cents"] for b in analytics["by_technician"])
    assert by_tech_total == analytics["confirmed_revenue_cents"]

    # The new booking is present in the backing rows.
    assert checkout["booking_id"] in {r["booking_id"] for r in analytics["rows"]}

    # A payment exception is visible and excluded from confirmed revenue.
    exceptions = [r for r in analytics["rows"] if r["status"] == "payment_exception"]
    assert exceptions, "the seeded payment exception must be visible"
    assert all(not r["counted_as_revenue"] for r in exceptions)
    assert analytics["exception_count"] == len(exceptions)


def test_timeline_and_analytics_agree_after_a_mutation(client, login):
    login("owner@northline.example")
    headers = _headers(client)
    before = client.get("/api/owner/timeline", headers=headers).json()
    blocked_before = [e for e in before["events"] if e["kind"] == "block"]
    assert blocked_before == []

    client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T13:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Family emergency",
        },
        headers=headers,
    )

    after = client.get("/api/owner/timeline?day=2026-11-05", headers=headers).json()
    blocks = [e for e in after["events"] if e["kind"] == "block"]
    assert len(blocks) == 1
    affected = [e for e in after["events"] if e["status"] == "needs_reassignment"]
    assert affected, "the affected booking must be visibly marked on the timeline"

    analytics = client.get(
        "/api/owner/analytics?date_from=2026-11-05&date_to=2026-11-05", headers=headers
    ).json()
    assert analytics["needs_reassignment_count"] >= 1


def test_demo_reset_endpoint_is_owner_only_and_restores_fixtures(client, login):
    login("maya@example.com")
    customer_headers = _headers(client)
    assert client.post("/api/owner/demo/reset", headers=customer_headers).status_code in (403, 404)

    login("owner@northline.example")
    owner_headers = _headers(client)
    resp = client.post("/api/owner/demo/reset", headers=owner_headers)
    assert resp.status_code == 200, resp.text

    login("maya@example.com")
    headers = _headers(client)
    listed = client.get("/api/bookings", headers=headers).json()
    assert listed, "seeded bookings must come back"
    assert all(b["reference"].startswith("SA-") for b in listed)
