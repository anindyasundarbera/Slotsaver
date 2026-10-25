"""A genuine concurrent HTTP race for one slot.

The sequential tests prove the database constraint. This one proves the
*server* behaves correctly under real parallel requests: two independent
sessions, released simultaneously by a barrier, one slot.

Both requests traverse the full stack (session, CSRF, validation, service layer,
transaction), so a check-then-insert regression anywhere above the index would
show up here.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.models import Booking, SlotBlock

SLOT = "2026-11-05T14:00:00Z"
SERVICE = "washer-repair"
TECHNICIAN = "tech_ana"


def _login(client, email: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return {"X-CSRF-Token": client.cookies.get("ss_csrf")}


def test_simultaneous_holds_for_one_slot_produce_exactly_one_winner(client, db):
    # Two separate TestClient instances = two independent cookie jars.
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    app = create_app(get_settings())
    clients = {}
    with TestClient(app) as maya_client, TestClient(app) as diego_client:
        clients["maya"] = (maya_client, _login(maya_client, "maya@example.com"))
        clients["diego"] = (diego_client, _login(diego_client, "diego@example.com"))

        barrier = threading.Barrier(2, timeout=10)

        def attempt(who: str) -> tuple[str, int, str]:
            http, headers = clients[who]
            payload = {
                "service_code": SERVICE,
                "technician_id": TECHNICIAN,
                "start_utc": SLOT,
            }
            barrier.wait()  # release both requests at the same instant
            resp = http.post("/api/holds", json=payload, headers=headers)
            code = ""
            if resp.status_code != 201:
                code = resp.json().get("error", {}).get("code", "")
            return who, resp.status_code, code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [f.result() for f in [pool.submit(attempt, "maya"), pool.submit(attempt, "diego")]]

    statuses = sorted(r[1] for r in results)
    assert statuses == [201, 409], f"expected exactly one winner, got {results}"

    winner = next(r for r in results if r[1] == 201)
    loser = next(r for r in results if r[1] == 409)
    assert loser[2] == "SLOT_UNAVAILABLE"

    # The database agrees: exactly one active claim on the 14:00 cell.
    db.expire_all()
    cells = db.execute(
        select(SlotBlock).where(
            SlotBlock.technician_id == TECHNICIAN,
            SlotBlock.slot_start_utc == __import__("datetime").datetime(2026, 11, 5, 14, 0,
                                                                        tzinfo=__import__("datetime").timezone.utc),
            SlotBlock.active == 1,
        )
    ).scalars().all()
    assert len(cells) == 1, f"exactly one owner must hold the cell, found {len(cells)}"

    winner_client, _ = clients[winner[0]]
    loser_client, _ = clients[loser[0]]
    winner_holds = winner_client.get("/api/bookings")
    loser_holds = loser_client.get("/api/bookings")
    assert winner_holds.status_code == 200 and loser_holds.status_code == 200
    # The loser holds no booking at that instant.
    loser_rows = [
        b for b in loser_holds.json()
        if b["start_utc"].startswith("2026-11-05T14:00")
    ]
    assert loser_rows == []


def test_capacity_index_itself_rejects_a_duplicate_claim(db):
    """Assert the database constraint directly, independent of service-layer checks.

    The HTTP race test above is end-to-end, but it can be satisfied by the service
    layer's pre-check rather than the index. This test bypasses `claim_cells`
    entirely and proves the partial unique index is what makes overbooking
    impossible: if someone makes that index non-unique, this fails.
    """
    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    from app.models import SlotBlock

    cell = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)
    db.add(
        SlotBlock(
            technician_id=TECHNICIAN,
            slot_start_utc=cell,
            owner_kind="booking",
            owner_id="bkg_first",
            active=1,
        )
    )
    db.commit()

    db.add(
        SlotBlock(
            technician_id=TECHNICIAN,
            slot_start_utc=cell,
            owner_kind="booking",
            owner_id="bkg_second",
            active=1,
        )
    )
    with __import__("pytest").raises(IntegrityError):
        db.commit()
    db.rollback()

    # A released cell may be re-claimed: the index is partial on active = 1.
    first = db.execute(
        select(SlotBlock).where(
            SlotBlock.technician_id == TECHNICIAN, SlotBlock.slot_start_utc == cell
        )
    ).scalar_one()
    first.active = 0
    db.commit()
    db.add(
        SlotBlock(
            technician_id=TECHNICIAN,
            slot_start_utc=cell,
            owner_kind="booking",
            owner_id="bkg_second",
            active=1,
        )
    )
    db.commit()
    active = db.execute(
        select(SlotBlock).where(
            SlotBlock.technician_id == TECHNICIAN, SlotBlock.slot_start_utc == cell
        )
    ).scalars().all()
    assert sum(1 for c in active if c.active == 1) == 1
