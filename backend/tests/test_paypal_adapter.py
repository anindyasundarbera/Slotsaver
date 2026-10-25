"""Hermetic tests for the real PayPal adapter using a stubbed HTTP transport.

These are NOT live sandbox evidence; see docs/integration-status.md.
"""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app.config import ConfigError, Settings
from app.errors import ProviderUnavailable
from app.services.payments import PayPalProvider, PaymentError, build_provider

ORDERS_CREATE = {
    "id": "5O190127TN364715T",
    "status": "CREATED",
    "links": [
        {"rel": "self", "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O1"},
        {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O1"},
    ],
    "purchase_units": [
        {
            "reference_id": "SA-ABC123",
            "custom_id": "pay_1",
            "invoice_id": "SA-ABC123",
            "amount": {"currency_code": "USD", "value": "75.00"},
            "payee": {"merchant_id": "MERCHANT1"},
        }
    ],
}

ORDERS_CAPTURED = {
    "id": "5O190127TN364715T",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "custom_id": "pay_1",
            "invoice_id": "SA-ABC123",
            "amount": {"currency_code": "USD", "value": "75.00"},
            "payee": {"merchant_id": "MERCHANT1"},
            "payments": {
                "captures": [
                    {
                        "id": "3C679366HH908993F",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "75.00"},
                    }
                ]
            },
        }
    ],
}


def _settings(**overrides) -> Settings:
    base = Settings(
        paypal_mode="sandbox",
        paypal_client_id="test-client",
        paypal_client_secret="test-secret",
        paypal_merchant_id="MERCHANT1",
        paypal_webhook_id="WH-1",
    )
    return replace(base, **overrides)


class RecordingTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def _token_then(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "A21AA-token", "expires_in": 32400})
        for path, response in routes.items():
            if request.url.path == path:
                return response
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

    return handler


def test_create_order_sends_server_amount_and_idempotency_header():
    transport = RecordingTransport(_token_then({"/v2/checkout/orders": httpx.Response(201, json=ORDERS_CREATE)}))
    provider = PayPalProvider(_settings(), transport=transport)
    order = provider.create_order(
        attempt_id="pay_1",
        amount_cents=7500,
        currency="USD",
        description="Washing machine repair",
        reference="SA-ABC123",
        idempotency_key="slotsaver:hold_1:bkg_1:1",
    )
    assert order.order_id == "5O190127TN364715T"
    assert order.approve_url and "sandbox.paypal.com" in order.approve_url

    create = [r for r in transport.requests if r.url.path == "/v2/checkout/orders"][0]
    assert create.headers["PayPal-Request-Id"] == "slotsaver:hold_1:bkg_1:1"
    body = json.loads(create.content)
    assert body["intent"] == "CAPTURE"
    unit = body["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "USD", "value": "75.00"}
    assert unit["custom_id"] == "pay_1"
    assert unit["invoice_id"] == "SA-ABC123"
    assert unit["payee"]["merchant_id"] == "MERCHANT1"
    # The client never supplies a price; the server does, from integer cents.
    assert "price" not in body


def test_capture_order_parses_settled_amount():
    transport = RecordingTransport(
        _token_then(
            {"/v2/checkout/orders/5O190127TN364715T/capture": httpx.Response(201, json=ORDERS_CAPTURED)}
        )
    )
    provider = PayPalProvider(_settings(), transport=transport)
    view = provider.capture_order("5O190127TN364715T", idempotency_key="cap-1")
    assert view.status == "COMPLETED"
    assert view.captured_amount_cents == 7500
    assert view.currency == "USD"
    assert view.capture_id == "3C679366HH908993F"
    assert view.payee_merchant_id == "MERCHANT1"
    assert view.custom_id == "pay_1"


def test_capture_rejection_raises_not_capturable():
    transport = RecordingTransport(
        _token_then(
            {
                "/v2/checkout/orders/5O1/capture": httpx.Response(
                    422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_NOT_APPROVED"}]}
                )
            }
        )
    )
    provider = PayPalProvider(_settings(), transport=transport)
    with pytest.raises(PaymentError) as excinfo:
        provider.capture_order("5O1", idempotency_key="cap-2")
    assert excinfo.value.code == "ORDER_NOT_CAPTURABLE"


def test_transport_failure_is_reported_as_ambiguous_capture():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        raise httpx.ConnectError("network down")

    provider = PayPalProvider(_settings(), transport=RecordingTransport(handler))
    with pytest.raises(ProviderUnavailable) as excinfo:
        provider.capture_order("5O1", idempotency_key="cap-3")
    assert excinfo.value.details.get("ambiguous") is True


def test_bad_credentials_raise_provider_unavailable():
    transport = RecordingTransport(lambda request: httpx.Response(401, json={"error": "invalid_client"}))
    provider = PayPalProvider(_settings(), transport=transport)
    with pytest.raises(ProviderUnavailable):
        provider.create_order(
            attempt_id="p",
            amount_cents=1,
            currency="USD",
            description="x",
            reference="r",
            idempotency_key="k",
        )


def test_webhook_verification_requires_all_signature_headers():
    provider = PayPalProvider(_settings(), transport=RecordingTransport(_token_then({})))
    assert provider.verify_webhook({}, b"{}") is False
    assert provider.verify_webhook({"paypal-auth-algo": "SHA256withRSA"}, b"{}") is False


def test_webhook_verification_calls_paypals_endpoint():
    transport = RecordingTransport(
        _token_then(
            {
                "/v1/notifications/verify-webhook-signature": httpx.Response(
                    200, json={"verification_status": "SUCCESS"}
                )
            }
        )
    )
    provider = PayPalProvider(_settings(), transport=transport)
    body = json.dumps({"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}).encode()
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api.paypal.com/cert",
        "paypal-transmission-id": "tid",
        "paypal-transmission-sig": "sig",
        "paypal-transmission-time": "2026-11-03T10:00:00Z",
    }
    assert provider.verify_webhook(headers, body) is True
    verify = [r for r in transport.requests if r.url.path.endswith("verify-webhook-signature")][0]
    sent = json.loads(verify.content)
    assert sent["webhook_id"] == "WH-1"
    assert sent["transmission_id"] == "tid"
    assert sent["webhook_event"]["id"] == "WH-1"


def test_webhook_verification_failure_is_rejected():
    transport = RecordingTransport(
        _token_then(
            {
                "/v1/notifications/verify-webhook-signature": httpx.Response(
                    200, json={"verification_status": "FAILURE"}
                )
            }
        )
    )
    provider = PayPalProvider(_settings(), transport=transport)
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api.paypal.com/cert",
        "paypal-transmission-id": "tid",
        "paypal-transmission-sig": "sig",
        "paypal-transmission-time": "2026-11-03T10:00:00Z",
    }
    assert provider.verify_webhook(headers, b'{"id":"WH-1"}') is False


def test_live_mode_is_refused_at_configuration(monkeypatch, tmp_path):
    from app.config import load_settings, reset_settings_cache

    monkeypatch.setenv("PAYPAL_MODE", "live")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "x")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "y")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "live" in str(excinfo.value)
    reset_settings_cache()


def test_sandbox_mode_requires_credentials(monkeypatch, tmp_path):
    from app.config import load_settings, reset_settings_cache

    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    reset_settings_cache()
    with pytest.raises(ConfigError):
        load_settings()
    reset_settings_cache()


def test_build_provider_respects_mode():
    assert build_provider(_settings()).mode == "sandbox"
    assert build_provider(Settings(paypal_mode="simulated")).mode == "simulated"
