"""PayPal integration readiness: config validation, preflight, keys, webhook gate.

Complements `test_paypal_adapter.py` (HTTP shape) with the operational contract:
distinct operation keys, the approved base origin, the enable flag, and the
guarantee that preflight never reveals a secret.
"""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app.config import SANDBOX_BASE_URL, ConfigError, Settings, is_placeholder, load_settings, reset_settings_cache
from app.preflight import main as preflight_main
from app.services.payments import PayPalProvider


def _sandbox(**overrides) -> Settings:
    base = Settings(
        paypal_mode="sandbox",
        paypal_client_id="client-id-value",
        paypal_client_secret="client-secret-value",
        paypal_merchant_id="MERCHANT1",
        paypal_webhook_id="WH-SUB-1",
        paypal_webhooks_enabled=True,
    )
    return replace(base, **overrides)


class RecordingTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def _router(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
        for path, response in routes.items():
            if request.url.path == path:
                return response
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

    return handler


ORDER = {
    "id": "ORDER1",
    "status": "CREATED",
    "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER1"}],
    "purchase_units": [
        {
            "custom_id": "pay_1",
            "invoice_id": "SA-1",
            "amount": {"currency_code": "USD", "value": "75.00"},
            "payee": {"merchant_id": "MERCHANT1"},
        }
    ],
}


# ---------------------------------------------------------------- placeholders
@pytest.mark.parametrize(
    "value",
    ["", "   ", None, "YOUR_CLIENT_ID", "replace-me", "changeme", "demo-webhook-secret", "TODO"],
)
def test_placeholders_are_detected(value):
    assert is_placeholder(value) is True


@pytest.mark.parametrize("value", ["AbC123", "sandbox-key-9f8e", "x" * 40])
def test_real_looking_values_are_not_placeholders(value):
    assert is_placeholder(value) is False


# ---------------------------------------------------------------- config gates
def test_live_mode_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYPAL_MODE", "live")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "a")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "b")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    with pytest.raises(ConfigError):
        load_settings()
    reset_settings_cache()


def test_non_sandbox_base_url_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "a")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "b")
    monkeypatch.setenv("PAYPAL_BASE_URL", "https://api-m.paypal.com")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "sandbox" in str(excinfo.value).lower()
    reset_settings_cache()


def test_sandbox_base_url_override_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "a")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "b")
    monkeypatch.setenv("PAYPAL_BASE_URL", SANDBOX_BASE_URL + "/")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    settings = load_settings()
    assert settings.paypal_base_url.rstrip("/") == SANDBOX_BASE_URL
    reset_settings_cache()


def test_simulated_mode_never_uses_a_published_webhook_key(settings):
    assert settings.simulated_webhook_secret != "demo-webhook-secret"
    assert len(settings.simulated_webhook_secret) >= 20


def test_webhooks_disabled_by_default_without_a_webhook_id(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYPAL_MODE", "simulated")
    monkeypatch.delenv("PAYPAL_WEBHOOKS_ENABLED", raising=False)
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    assert load_settings().paypal_webhooks_enabled is False
    reset_settings_cache()


# ---------------------------------------------------------------- order body
def test_order_uses_experience_context_when_callbacks_configured():
    settings = _sandbox(
        paypal_return_url="http://localhost:4200/checkout/return",
        paypal_cancel_url="http://localhost:4200/checkout/cancel",
    )
    transport = RecordingTransport(_router({"/v2/checkout/orders": httpx.Response(201, json=ORDER)}))
    provider = PayPalProvider(settings, transport=transport)
    provider.create_order(
        attempt_id="pay_1",
        amount_cents=7500,
        currency="USD",
        description="Washing machine repair",
        reference="SA-1",
        idempotency_key="create-key",
    )
    body = json.loads([r for r in transport.requests if r.url.path == "/v2/checkout/orders"][0].content)
    ctx = body["payment_source"]["paypal"]["experience_context"]
    assert ctx["return_url"].endswith("/checkout/return")
    assert ctx["cancel_url"].endswith("/checkout/cancel")
    assert "application_context" not in body, "the deprecated block must not compete with the new one"


def test_order_falls_back_to_application_context_without_callbacks():
    transport = RecordingTransport(_router({"/v2/checkout/orders": httpx.Response(201, json=ORDER)}))
    provider = PayPalProvider(_sandbox(), transport=transport)
    provider.create_order(
        attempt_id="pay_1",
        amount_cents=7500,
        currency="USD",
        description="d",
        reference="SA-1",
        idempotency_key="create-key",
    )
    body = json.loads([r for r in transport.requests if r.url.path == "/v2/checkout/orders"][0].content)
    assert "payment_source" not in body
    assert body["application_context"]["user_action"] == "PAY_NOW"


def test_price_always_comes_from_integer_cents():
    transport = RecordingTransport(_router({"/v2/checkout/orders": httpx.Response(201, json=ORDER)}))
    provider = PayPalProvider(_sandbox(), transport=transport)
    provider.create_order(
        attempt_id="pay_1", amount_cents=12345, currency="USD",
        description="d", reference="SA-1", idempotency_key="k",
    )
    body = json.loads([r for r in transport.requests if r.url.path == "/v2/checkout/orders"][0].content)
    assert body["purchase_units"][0]["amount"]["value"] == "123.45"


# ---------------------------------------------------------------- keys
def test_create_and_capture_use_distinct_idempotency_keys(client, login, db):
    from sqlalchemy import select

    from app.models import PaymentAttempt

    login("maya@example.com")
    headers = {"X-CSRF-Token": client.cookies.get("ss_csrf")}
    reply = client.post(
        "/api/assistant/message", json={"message": "dryer repair tomorrow after 9 AM"}, headers=headers
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

    attempt = db.get(PaymentAttempt, checkout["attempt_id"])
    assert attempt.idempotency_key.endswith(":create")

    from app.services.bookings import _capture_key

    capture_key = _capture_key(attempt)
    assert capture_key != attempt.idempotency_key
    assert capture_key.endswith(":capture")


# ---------------------------------------------------------------- webhook gate
def test_webhook_intake_refuses_when_disabled(settings):
    from fastapi.testclient import TestClient

    from app.db import Base, get_engine, make_session_factory
    from app.main import create_app
    from app.seed import seed_database

    disabled = replace(settings, paypal_webhooks_enabled=False)
    engine = get_engine(disabled.database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as db:
        seed_database(db, disabled)
        db.commit()

    with TestClient(create_app(disabled)) as client:
        resp = client.post(
            "/api/webhooks/paypal",
            content=b'{"id":"WH-1","event_type":"PAYMENT.CAPTURE.COMPLETED"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "WEBHOOKS_DISABLED"


def test_config_reports_webhook_support_honestly(client):
    payload = client.get("/api/config").json()
    # simulated mode is never reported as webhook-capable
    assert payload["supports_webhooks"] is False


# ---------------------------------------------------------------- preflight
def _preflight(monkeypatch, tmp_path, capsys, env: dict[str, str], args: list[str] | None = None) -> tuple[int, str]:
    base = {
        "DATABASE_URL": f"sqlite:///{tmp_path}/pf.db",
        "PAYPAL_MODE": "simulated",
        "SEED_DEMO_DATA": "0",
    }
    base.update(env)
    # Start from a clean slate so the global test env cannot mask a status.
    for key in (
        "PAYPAL_WEBHOOKS_ENABLED",
        "PAYPAL_WEBHOOK_ID",
        "PAYPAL_MERCHANT_ID",
        "PAYPAL_BASE_URL",
        "PAYPAL_RETURN_URL",
        "PAYPAL_CANCEL_URL",
        "LLM_API_KEY",
        "SIMULATED_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in base.items():
        monkeypatch.setenv(key, value)
    reset_settings_cache()
    code = preflight_main(args or [])
    captured = capsys.readouterr()
    reset_settings_cache()
    return code, captured.out + captured.err


def test_preflight_never_prints_secret_values(monkeypatch, tmp_path, capsys):
    secrets = {
        "PAYPAL_MODE": "sandbox",
        "PAYPAL_CLIENT_ID": "AbC123SecretLookingValue",
        "PAYPAL_CLIENT_SECRET": "SuperSecret987",
        "PAYPAL_MERCHANT_ID": "MERCHANTXYZ",
        "PAYPAL_WEBHOOKS_ENABLED": "true",
        "PAYPAL_WEBHOOK_ID": "WH-ABC-123",
    }
    code, output = _preflight(monkeypatch, tmp_path, capsys, secrets)
    assert code == 0
    for value in ("AbC123SecretLookingValue", "SuperSecret987", "MERCHANTXYZ", "WH-ABC-123"):
        assert value not in output, f"preflight leaked {value}"


def test_preflight_reports_missing_names_only(monkeypatch, tmp_path, capsys):
    code, output = _preflight(
        monkeypatch,
        tmp_path,
        capsys,
        {"PAYPAL_MODE": "sandbox", "PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": ""},
    )
    assert code == 1
    assert "PAYPAL_CLIENT_ID" in output
    assert "MISSING" in output


def test_preflight_json_is_machine_readable_and_sanitized(monkeypatch, tmp_path, capsys):
    code, output = _preflight(
        monkeypatch,
        tmp_path,
        capsys,
        {"PAYPAL_MODE": "sandbox", "PAYPAL_CLIENT_ID": "IdValue123", "PAYPAL_CLIENT_SECRET": "SecValue456"},
        args=["--json"],
    )
    payload = json.loads(output)
    assert isinstance(payload, list) and payload
    assert all({"name", "status"} <= set(item) for item in payload)
    assert "IdValue123" not in output and "SecValue456" not in output


def test_preflight_network_check_is_not_run_without_credentials(monkeypatch, tmp_path, capsys):
    code, output = _preflight(
        monkeypatch,
        tmp_path,
        capsys,
        {"PAYPAL_MODE": "simulated", "PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": ""},
        args=["--network"],
    )
    assert "paypal_oauth: NOT_RUN" in output


def test_preflight_network_auth_failure_reports_status_not_body(monkeypatch, tmp_path, capsys):
    import app.preflight as preflight_module

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return httpx.Response(401, json={"error": "invalid_client", "error_description": "hunter2"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    code, output = _preflight(
        monkeypatch,
        tmp_path,
        capsys,
        {"PAYPAL_MODE": "sandbox", "PAYPAL_CLIENT_ID": "IdValue123", "PAYPAL_CLIENT_SECRET": "SecValue456"},
        args=["--network"],
    )
    assert "FAILED" in output
    assert "401" in output
    assert "hunter2" not in output
    assert code == 1


def test_preflight_network_success_reports_authenticated(monkeypatch, tmp_path, capsys):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return httpx.Response(200, json={"access_token": "SECRET-TOKEN", "expires_in": 300, "scope": "a b c"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    code, output = _preflight(
        monkeypatch,
        tmp_path,
        capsys,
        {
            "PAYPAL_MODE": "sandbox",
            "PAYPAL_CLIENT_ID": "IdValue123",
            "PAYPAL_CLIENT_SECRET": "SecValue456",
            "PAYPAL_MERCHANT_ID": "MERCHANT1",
        },
        args=["--network"],
    )
    assert "AUTHENTICATED" in output
    assert "SECRET-TOKEN" not in output
    assert code == 0


# ---------------------------------------------------------------- base-url diagnostics
@pytest.mark.parametrize(
    "wrong,expect",
    [
        ("https://sandbox.paypal.com", "buyer-facing"),
        ("https://www.sandbox.paypal.com", "checkout page"),
        ("https://api-m.paypal.com", "LIVE"),
        ("https://api.paypal.com", "LIVE"),
    ],
)
def test_common_wrong_hosts_get_a_specific_message(monkeypatch, tmp_path, wrong, expect):
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "a")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "b")
    monkeypatch.setenv("PAYPAL_BASE_URL", wrong)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert expect in str(excinfo.value)
    reset_settings_cache()


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_base_url_is_allowed_and_means_default(monkeypatch, tmp_path, value):
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "a")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "b")
    monkeypatch.setenv("PAYPAL_BASE_URL", value)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    settings = load_settings()
    assert settings.paypal_base_url == SANDBOX_BASE_URL
    reset_settings_cache()


def test_legacy_api_alias_is_accepted_and_normalised(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "a")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "b")
    monkeypatch.setenv("PAYPAL_BASE_URL", "https://api.sandbox.paypal.com")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    settings = load_settings()
    # The client always talks to one canonical origin.
    assert settings.paypal_base_url == SANDBOX_BASE_URL
    reset_settings_cache()
