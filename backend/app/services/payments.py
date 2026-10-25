from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

import httpx

from ..config import Settings
from ..errors import AppError, ProviderUnavailable, Validation

log = logging.getLogger("slotsaver.payments")


class PaymentError(AppError):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None) -> None:
        super().__init__(code, message, status_code, details or {})


@dataclass
class OrderView:
    order_id: str
    status: str
    approve_url: str | None
    capture_id: str | None
    captured_amount_cents: int | None
    currency: str
    payee_merchant_id: str | None
    custom_id: str | None
    invoice_id: str | None
    raw: dict


class PaymentProvider(Protocol):
    mode: str

    def create_order(self, *, attempt_id: str, amount_cents: int, currency: str, description: str, reference: str, idempotency_key: str) -> OrderView: ...
    def get_order(self, order_id: str) -> OrderView: ...
    def capture_order(self, order_id: str, *, idempotency_key: str) -> OrderView: ...
    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool: ...


def _amount_to_minor(value: dict | None) -> int | None:
    if not value:
        return None
    try:
        amount = Decimal(str(value.get("value")))
    except Exception:
        return None
    return int((amount * 100).to_integral_value())


class SimulatedProvider:
    """Clearly labelled offline substitute. Never presented as payment evidence."""

    mode = "simulated"

    def __init__(self, settings: Settings, order_store: dict[str, dict] | None = None) -> None:
        self.settings = settings
        self._orders: dict[str, dict] = order_store if order_store is not None else {}

    def _new_id(self, prefix: str) -> str:
        import secrets

        return f"{prefix}{secrets.token_hex(8).upper()}"

    def create_order(self, *, attempt_id, amount_cents, currency, description, reference, idempotency_key) -> OrderView:
        for existing in self._orders.values():
            if existing["idempotency_key"] == idempotency_key:
                return self._view(existing)
        order_id = self._new_id("SIMORDER")
        record = {
            "id": order_id,
            "attempt_id": attempt_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "description": description,
            "reference": reference,
            "idempotency_key": idempotency_key,
            "status": "CREATED",
            "capture_id": None,
            "captured_amount_cents": None,
            "payee_merchant_id": self.settings.paypal_merchant_id or "SIMULATED-MERCHANT",
            "custom_id": attempt_id,
            "invoice_id": reference,
            "capture_calls": 0,
            "cancelled": False,
        }
        self._orders[order_id] = record
        return self._view(record)

    def _view(self, record: dict) -> OrderView:
        return OrderView(
            order_id=record["id"],
            status=record["status"],
            approve_url=f"/simulated-checkout?order={record['id']}",
            capture_id=record["capture_id"],
            captured_amount_cents=record["captured_amount_cents"],
            currency=record["currency"],
            payee_merchant_id=record["payee_merchant_id"],
            custom_id=record["custom_id"],
            invoice_id=record["invoice_id"],
            raw={k: v for k, v in record.items() if k != "idempotency_key"},
        )

    def get_order(self, order_id: str) -> OrderView:
        record = self._orders.get(order_id)
        if record is None:
            raise PaymentError("ORDER_NOT_FOUND", "Unknown simulated order.", 404)
        return self._view(record)

    def cancel_order(self, order_id: str) -> OrderView:
        record = self._orders.get(order_id)
        if record is None:
            raise PaymentError("ORDER_NOT_FOUND", "Unknown simulated order.", 404)
        if record["status"] in {"CREATED", "APPROVED"}:
            record["status"] = "VOIDED"
            record["cancelled"] = True
        return self._view(record)

    def capture_order(self, order_id: str, *, idempotency_key: str) -> OrderView:
        record = self._orders.get(order_id)
        if record is None:
            raise PaymentError("ORDER_NOT_FOUND", "Unknown simulated order.", 404)
        record["capture_calls"] = int(record.get("capture_calls", 0)) + 1
        if record["status"] == "COMPLETED":
            return self._view(record)
        if record["status"] in {"VOIDED", "CANCELLED"}:
            raise PaymentError("ORDER_NOT_PAYABLE", "The order was cancelled or voided.", 409)
        if record["status"] == "CREATED":
            # Sandbox parity: PayPal requires an approved order before capture.
            raise PaymentError("ORDER_NOT_APPROVED", "The buyer has not approved this order yet.", 409)
        record["status"] = "COMPLETED"
        record["capture_id"] = self._new_id("SIMCAP")
        record["captured_amount_cents"] = record["amount_cents"]
        return self._view(record)

    def approve(self, order_id: str) -> OrderView:
        record = self._orders.get(order_id)
        if record is None:
            raise PaymentError("ORDER_NOT_FOUND", "Unknown simulated order.", 404)
        if record["status"] == "CREATED":
            record["status"] = "APPROVED"
        return self._view(record)

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        signature = headers.get("paypal-transmission-sig", "")
        expected = hmac.new(
            self.settings.simulated_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)


class PayPalProvider:
    """Real PayPal Orders v2 client. Sandbox only; refuses live mode."""

    mode = "sandbox"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if settings.paypal_mode != "sandbox":
            raise Validation("PayPalProvider requires PAYPAL_MODE=sandbox")
        self.settings = settings
        self.base_url = settings.paypal_base_url
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.settings.paypal_timeout_seconds,
            transport=self._transport,
        )

    def _access_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token
        try:
            with self._client() as client:
                resp = client.post(
                    "/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    auth=(self.settings.paypal_client_id, self.settings.paypal_client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            log.warning("paypal token request failed: %s", type(exc).__name__)
            raise ProviderUnavailable("Could not reach PayPal to obtain an access token.") from exc
        if resp.status_code != 200:
            log.warning("paypal token rejected status=%s", resp.status_code)
            raise ProviderUnavailable("PayPal rejected the API credentials.")
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = now + timedelta(seconds=max(60, int(payload.get("expires_in", 300)) - 60))
        return self._token

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key[:108]
        return headers

    @staticmethod
    def _parse(payload: dict) -> OrderView:
        units = payload.get("purchase_units") or [{}]
        unit = units[0] if units else {}
        captures = ((unit.get("payments") or {}).get("captures") or [])
        capture = captures[0] if captures else {}
        approve_url = None
        for link in payload.get("links") or []:
            if link.get("rel") in {"approve", "payer-action"}:
                approve_url = link.get("href")
                break
        payee = (unit.get("payee") or {}).get("merchant_id") or (payload.get("payee") or {}).get("merchant_id")
        return OrderView(
            order_id=payload.get("id", ""),
            status=payload.get("status", ""),
            approve_url=approve_url,
            capture_id=capture.get("id"),
            captured_amount_cents=_amount_to_minor(capture.get("amount")),
            currency=(capture.get("amount") or {}).get("currency_code")
            or (unit.get("amount") or {}).get("currency_code", ""),
            payee_merchant_id=payee,
            custom_id=unit.get("custom_id"),
            invoice_id=unit.get("invoice_id"),
            raw=payload,
        )

    def create_order(self, *, attempt_id, amount_cents, currency, description, reference, idempotency_key) -> OrderView:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference,
                    "custom_id": attempt_id,
                    "invoice_id": reference,
                    "description": description[:127],
                    "amount": {
                        "currency_code": currency,
                        "value": f"{Decimal(amount_cents) / 100:.2f}",
                    },
                }
            ],
        }
        # `application_context.return_url` is deprecated in favour of the
        # payment-source experience context. Only send it when the operator has
        # configured a real return/cancel route; otherwise we keep the plain
        # approval-link flow the UI already drives.
        if self.settings.paypal_return_url and self.settings.paypal_cancel_url:
            body["payment_source"] = {
                "paypal": {
                    "experience_context": {
                        "brand_name": self.settings.business_name,
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                        "return_url": self.settings.paypal_return_url,
                        "cancel_url": self.settings.paypal_cancel_url,
                    }
                }
            }
        else:
            body["application_context"] = {
                "brand_name": self.settings.business_name,
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
            }
        if self.settings.paypal_merchant_id:
            body["purchase_units"][0]["payee"] = {"merchant_id": self.settings.paypal_merchant_id}
        try:
            with self._client() as client:
                resp = client.post("/v2/checkout/orders", json=body, headers=self._headers(idempotency_key))
        except httpx.HTTPError as exc:
            log.warning("paypal create order failed: %s", type(exc).__name__)
            raise ProviderUnavailable("Could not reach PayPal to create the order.") from exc
        if resp.status_code not in (200, 201):
            log.warning("paypal create order rejected status=%s", resp.status_code)
            raise ProviderUnavailable("PayPal rejected the order creation request.")
        return self._parse(resp.json())

    def get_order(self, order_id: str) -> OrderView:
        try:
            with self._client() as client:
                resp = client.get(f"/v2/checkout/orders/{order_id}", headers=self._headers())
        except httpx.HTTPError as exc:
            log.warning("paypal get order failed: %s", type(exc).__name__)
            raise ProviderUnavailable("Could not reach PayPal to read the order.") from exc
        if resp.status_code == 404:
            raise PaymentError("ORDER_NOT_FOUND", "PayPal does not know this order for this merchant.", 404)
        if resp.status_code != 200:
            raise ProviderUnavailable("PayPal could not return the order.")
        return self._parse(resp.json())

    def capture_order(self, order_id: str, *, idempotency_key: str) -> OrderView:
        try:
            with self._client() as client:
                resp = client.post(
                    f"/v2/checkout/orders/{order_id}/capture",
                    headers=self._headers(idempotency_key),
                )
        except httpx.HTTPError as exc:
            log.warning("paypal capture failed: %s", type(exc).__name__)
            raise ProviderUnavailable("Capture outcome is unknown: PayPal was unreachable.", {"ambiguous": True}) from exc
        if resp.status_code in (200, 201):
            return self._parse(resp.json())
        if resp.status_code == 422:
            raise PaymentError("ORDER_NOT_CAPTURABLE", "PayPal reports this order cannot be captured.", 409)
        if resp.status_code == 404:
            raise PaymentError("ORDER_NOT_FOUND", "PayPal does not know this order for this merchant.", 404)
        raise ProviderUnavailable("PayPal could not process the capture.", {"ambiguous": resp.status_code >= 500})

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        required = {
            "paypal-auth-algo": headers.get("paypal-auth-algo"),
            "paypal-cert-url": headers.get("paypal-cert-url"),
            "paypal-transmission-id": headers.get("paypal-transmission-id"),
            "paypal-transmission-sig": headers.get("paypal-transmission-sig"),
            "paypal-transmission-time": headers.get("paypal-transmission-time"),
        }
        if any(v is None for v in required.values()) or not self.settings.paypal_webhook_id:
            return False
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            return False
        payload = {
            "auth_algo": required["paypal-auth-algo"],
            "cert_url": required["paypal-cert-url"],
            "transmission_id": required["paypal-transmission-id"],
            "transmission_sig": required["paypal-transmission-sig"],
            "transmission_time": required["paypal-transmission-time"],
            "webhook_id": self.settings.paypal_webhook_id,
            "webhook_event": event,
        }
        try:
            with self._client() as client:
                resp = client.post(
                    "/v1/notifications/verify-webhook-signature",
                    json=payload,
                    headers=self._headers(),
                )
        except httpx.HTTPError:
            log.warning("paypal webhook verification unreachable")
            return False
        if resp.status_code != 200:
            return False
        return resp.json().get("verification_status") == "SUCCESS"


def build_provider(settings: Settings, simulated_store: dict | None = None) -> PaymentProvider:
    if settings.paypal_mode == "sandbox":
        return PayPalProvider(settings)
    return SimulatedProvider(settings, simulated_store)
