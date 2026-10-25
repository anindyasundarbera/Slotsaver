"""Mandatory evidence: disruption -> proposal -> explicit approval -> persisted replacement."""
from __future__ import annotations

from sqlalchemy import select

from app.models import (
    Booking,
    BookingStatus,
    ProposalStatus,
    ReassignmentProposal,
    TechnicianBlock,
    User,
)


def _headers(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def _confirmed_booking(db, reference="SA-D4E5F6") -> Booking:
    return db.execute(select(Booking).where(Booking.reference == reference)).scalar_one()


def test_owner_disruption_creates_proposal_and_preserves_paid_booking(client, login, db):
    booking = _confirmed_booking(db)
    booking_id = booking.id
    original_technician = booking.technician_id
    price = booking.price_cents

    login("owner@northline.example")
    headers = _headers(client)
    resp = client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T13:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Family emergency",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert booking_id in result["affected_booking_ids"]
    assert result["proposals_created"]

    db.expire_all()
    updated = db.get(Booking, booking_id)
    assert updated.status == BookingStatus.needs_reassignment.value
    assert updated.technician_id == original_technician, "the booking is preserved until approval"
    assert updated.price_cents == price
    proposal = db.execute(
        select(ReassignmentProposal).where(ReassignmentProposal.booking_id == booking_id)
    ).scalars().first()
    assert proposal is not None
    assert proposal.status in {ProposalStatus.proposed.value, ProposalStatus.unresolved.value}
    assert db.execute(select(TechnicianBlock)).scalars().first() is not None


def test_customer_approval_persists_the_replacement(client, login, db):
    booking = _confirmed_booking(db)
    booking_id, original = booking.id, booking.technician_id

    login("owner@nightline.example") if False else login("owner@northline.example")
    owner_headers = _headers(client)
    client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T13:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Family emergency",
        },
        headers=owner_headers,
    )
    client.post("/api/auth/logout", headers=owner_headers)

    login("maya@example.com")
    headers = _headers(client)
    mine = [b for b in client.get("/api/bookings", headers=headers).json() if b["id"] == booking_id]
    assert mine, "Maya owns this seeded booking"
    proposal = mine[0]["proposal"]
    assert proposal is not None
    assert proposal["status"] == "proposed"
    replacement = next(c for c in proposal["candidates"] if c["available"])

    approve = client.post(
        f"/api/bookings/{booking_id}/reassignment/approve",
        json={"proposal_id": proposal["id"], "technician_id": replacement["technician_id"]},
        headers=headers,
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["status"] == "confirmed"
    assert body["technician_id"] == replacement["technician_id"]
    assert body["technician_id"] != original
    assert body["needs_attention"] is False

    db.expire_all()
    stored = db.get(Booking, booking_id)
    assert stored.status == BookingStatus.confirmed.value
    assert stored.technician_id == replacement["technician_id"]
    assert stored.price_cents == body["price_cents"], "price is unchanged by reassignment"


def test_customer_decline_keeps_booking_unresolved(client, login, db):
    booking = _confirmed_booking(db)
    booking_id = booking.id
    login("owner@northline.example")
    owner_headers = _headers(client)
    client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T13:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Family emergency",
        },
        headers=owner_headers,
    )
    client.post("/api/auth/logout", headers=owner_headers)

    login("maya@example.com")
    headers = _headers(client)
    booking_payload = [b for b in client.get("/api/bookings", headers=headers).json() if b["id"] == booking_id][0]
    proposal = booking_payload["proposal"]

    decline = client.post(
        f"/api/bookings/{booking_id}/reassignment/decline",
        json={"proposal_id": proposal["id"]},
        headers=headers,
    )
    assert decline.status_code == 200
    assert decline.json()["status"] == "needs_reassignment"
    assert decline.json()["needs_attention"] is True

    db.expire_all()
    assert db.get(Booking, booking_id).status == BookingStatus.needs_reassignment.value


def test_customer_cannot_approve_someone_elses_reassignment(client, login, db):
    booking = _confirmed_booking(db)
    booking_id = booking.id
    login("owner@northline.example")
    owner_headers = _headers(client)
    client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T13:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Family emergency",
        },
        headers=owner_headers,
    )
    client.post("/api/auth/logout", headers=owner_headers)

    proposal = db.execute(
        select(ReassignmentProposal).where(ReassignmentProposal.booking_id == booking_id)
    ).scalars().first()
    candidate = next(c for c in proposal.candidates if c["available"])

    login("diego@example.com")
    resp = client.post(
        f"/api/bookings/{booking_id}/reassignment/approve",
        json={"proposal_id": proposal.id, "technician_id": candidate["technician_id"]},
        headers=_headers(client),
    )
    assert resp.status_code == 404
    db.expire_all()
    assert db.get(Booking, booking_id).technician_id == "tech_ana"


def test_unoffered_technician_cannot_be_selected(client, login, db):
    booking = _confirmed_booking(db)
    booking_id = booking.id
    login("owner@northline.example")
    owner_headers = _headers(client)
    client.post(
        "/api/owner/technicians/tech_ana/unavailable",
        json={
            "start_utc": "2026-11-05T13:00:00-05:00",
            "end_utc": "2026-11-05T18:00:00-05:00",
            "reason": "Family emergency",
        },
        headers=owner_headers,
    )
    client.post("/api/auth/logout", headers=owner_headers)
    login("maya@example.com")
    headers = _headers(client)
    proposal = [b for b in client.get("/api/bookings", headers=headers).json() if b["id"] == booking_id][0]["proposal"]

    resp = client.post(
        f"/api/bookings/{booking_id}/reassignment/approve",
        json={"proposal_id": proposal["id"], "technician_id": "tech_ana"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CANDIDATE_NOT_OFFERED"


def test_no_qualified_alternative_is_reported_honestly(tmp_path, monkeypatch, settings):
    """When every alternative is busy, the proposal must be 'unresolved', not fabricated."""
    from app.db import Base, get_engine, make_session_factory
    from app.models import Hold, HoldStatus, SlotBlock, Technician
    from app.seed import seed_database
    from app.services import reassignment
    from app.timeutil import slot_starts
    from app.db import utcnow
    from datetime import timedelta

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    db = factory()
    seed_database(db, settings)
    db.commit()

    booking = db.execute(select(Booking).where(Booking.reference == "SA-D4E5F6")).scalar_one()
    owner = db.execute(select(User).where(User.role == "owner")).scalar_one()

    # Occupy every other qualified technician at that exact time.
    others = db.execute(
        select(Technician).where(Technician.id != booking.technician_id)
    ).scalars().all()
    for tech in others:
        hold = Hold(
            customer_id=booking.customer_id,
            technician_id=tech.id,
            service_id=booking.service_id,
            start_utc=booking.start_utc,
            end_utc=booking.end_utc,
            price_cents=booking.price_cents,
            currency="USD",
            status=HoldStatus.active.value,
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=30),
        )
        db.add(hold)
        db.flush()
        for slot in slot_starts(booking.start_utc, booking.end_utc):
            db.add(SlotBlock(
                technician_id=tech.id, slot_start_utc=slot,
                owner_kind="hold", owner_id=hold.id, active=1,
            ))
    db.commit()

    result = reassignment.mark_unavailable(
        db,
        settings,
        owner=owner,
        technician_id=booking.technician_id,
        start_utc=booking.start_utc,
        end_utc=booking.end_utc,
        reason="Sick",
    )
    db.commit()

    assert result["unresolved_booking_ids"] == [booking.id]
    proposal = db.execute(
        select(ReassignmentProposal).where(ReassignmentProposal.booking_id == booking.id)
    ).scalars().first()
    assert proposal.status == ProposalStatus.unresolved.value
    assert not any(c["available"] for c in proposal.candidates)
    db.close()
