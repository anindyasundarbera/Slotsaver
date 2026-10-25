from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    # Keep tests hermetic: a developer's populated backend/.env must never leak
    # into the suite. Must be set before app.config is imported.
    os.environ["SLOTSAVER_SKIP_DOTENV"] = "1"
    os.environ.setdefault("PAYPAL_MODE", "simulated")
    os.environ.setdefault("ASSISTANT_MODE", "scripted")
    os.environ.setdefault("DEMO_DATE", "2026-11-03")
    os.environ.setdefault("PAYPAL_WEBHOOKS_ENABLED", "true")


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The limiter is process-global by design; isolate tests from each other."""
    from app.security import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    from app.config import load_settings, reset_settings_cache
    from app.db import dispose_engines
    from app.deps import reset_factory

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("PAYPAL_MODE", "simulated")
    monkeypatch.setenv("ASSISTANT_MODE", "scripted")
    monkeypatch.setenv("DEMO_DATE", "2026-11-03")
    monkeypatch.setenv("SEED_DEMO_DATA", "0")
    # Tests sign their own simulated webhooks, so they need a known key.
    monkeypatch.setenv("SIMULATED_WEBHOOK_SECRET", "test-only-hmac-key-not-a-real-secret")
    # Webhook intake is opt-in; the webhook tests assert its behaviour explicitly.
    monkeypatch.setenv("PAYPAL_WEBHOOKS_ENABLED", "true")
    reset_settings_cache()
    dispose_engines()
    reset_factory()
    value = load_settings()
    yield value
    dispose_engines()
    reset_factory()
    reset_settings_cache()


@pytest.fixture()
def db(settings):
    from app.db import Base, get_engine, make_session_factory
    from app.seed import seed_database

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    seed_database(session, settings)
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(settings):
    from fastapi.testclient import TestClient

    from app.db import Base, get_engine, make_session_factory
    from app.main import create_app
    from app.seed import seed_database

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        seed_database(session, settings)
        session.commit()

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def login(client):
    def _login(email: str):
        resp = client.post("/api/auth/login", json={"email": email})
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _login


@pytest.fixture()
def csrf(client):
    def _header() -> dict:
        token = client.cookies.get("ss_csrf")
        return {"X-CSRF-Token": token or ""}

    return _header
