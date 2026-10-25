"""Secrets-safe capability preflight.

Prints only statuses and the *names* of missing variables. It never prints a
value, a prefix, a hash, an Authorization header, a payload, or any URL that
could contain a token. `--network` performs an OAuth-only authentication check;
it never creates or captures an order and never registers a webhook.

Usage:
    python -m app.preflight            # static, no network
    python -m app.preflight --network  # adds an OAuth exchange
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

from .config import SANDBOX_BASE_URL, ConfigError, Settings, is_placeholder, load_settings

OK = "OK"
MISSING = "MISSING"
DISABLED = "DISABLED"
NOT_RUN = "NOT_RUN"
UNSUPPORTED = "UNSUPPORTED"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    def render(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.name}: {self.status}{suffix}"


def _configured(value: str) -> bool:
    return not is_placeholder(value)


def static_checks(settings: Settings) -> list[Check]:
    checks: list[Check] = []

    checks.append(
        Check(
            "paypal_mode",
            "SANDBOX" if settings.paypal_mode == "sandbox" else "SIMULATED",
            "offline rehearsal" if settings.paypal_mode == "simulated" else "connected",
        )
    )

    missing = [
        name
        for name, value in (
            ("PAYPAL_CLIENT_ID", settings.paypal_client_id),
            ("PAYPAL_CLIENT_SECRET", settings.paypal_client_secret),
        )
        if not _configured(value)
    ]
    if settings.paypal_mode == "sandbox":
        checks.append(
            Check("paypal_auth_config", OK if not missing else MISSING, ", ".join(missing) or "both present")
        )
    else:
        checks.append(
            Check("paypal_auth_config", DISABLED, "not required in simulated mode")
        )

    origin = settings.paypal_base_url.rstrip("/")
    checks.append(
        Check(
            "paypal_base_url",
            OK if origin == SANDBOX_BASE_URL else UNSUPPORTED,
            "approved sandbox origin" if origin == SANDBOX_BASE_URL else "not the approved sandbox origin",
        )
    )

    checks.append(
        Check(
            "paypal_merchant_identity",
            OK if _configured(settings.paypal_merchant_id) else MISSING,
            "" if _configured(settings.paypal_merchant_id) else "PAYPAL_MERCHANT_ID",
        )
    )
    # The buyer-step failure UNSUPPORTED_PAYEE_CURRENCY cannot be detected from the
    # create-order response, so surface the pair the operator must keep consistent:
    # the seller account behind PAYPAL_MERCHANT_ID must settle in `currency`.
    # The merchant id itself is never printed (preflight output must stay value-free).
    if settings.paypal_mode == "sandbox" and _configured(settings.paypal_merchant_id):
        checks.append(
            Check(
                "paypal_payee_currency",
                OK,
                f"orders are created in {settings.currency}; the sandbox BUSINESS account behind "
                f"PAYPAL_MERCHANT_ID must support {settings.currency}, or the buyer page fails with "
                "UNSUPPORTED_PAYEE_CURRENCY",
            )
        )

    if settings.paypal_webhooks_enabled:
        checks.append(
            Check(
                "paypal_webhooks",
                OK
                if (settings.paypal_mode == "sandbox" and _configured(settings.paypal_webhook_id))
                else MISSING,
                "" if settings.paypal_mode == "sandbox" else "requires PAYPAL_MODE=sandbox",
            )
        )
        checks.append(
            Check(
                "paypal_webhook_url",
                OK if _configured(settings.paypal_webhook_url_effective) else MISSING,
                "" if _configured(settings.paypal_webhook_url_effective) else "PAYPAL_WEBHOOK_URL",
            )
        )
    else:
        checks.append(Check("paypal_webhooks", DISABLED, "server-side capture/reconcile only"))

    if settings.paypal_mode == "simulated":
        generated = settings.simulated_webhook_secret_generated
        checks.append(
            Check(
                "simulated_webhook_key",
                "RANDOM_PER_PROCESS"
                if generated
                else (OK if _configured(settings.simulated_webhook_secret) else MISSING),
                "generated at startup; not shared with any client"
                if generated
                else ("operator-provided" if not generated else ""),
            )
        )

    checks.append(
        Check(
            "paypal_callback_urls",
            OK
            if settings.paypal_return_url and settings.paypal_cancel_url
            else "OPTIONAL_MISSING",
            "",
        )
    )

    checks.append(
        Check(
            "assistant_runtime",
            OK,
            settings.assistant_mode
            + ("" if settings.assistant_mode != "llm" else
               ("" if _configured(settings.llm_api_key) else f"; {MISSING} LLM_API_KEY")),
        )
    )

    checks.append(Check("bryntum", "ENABLED" if settings.enable_bryntum else DISABLED, "trial build" if settings.enable_bryntum else ""))

    for name, enabled in (
        ("ag_studio", False),
        ("astropods", False),
        ("channel3", False),
        ("elastic", False),
        ("kernel", False),
        ("zapier", False),
    ):
        checks.append(Check(f"optional_{name}", "DEFERRED", "not selected for this build"))

    checks.append(Check("database", OK, settings.database_url.split("///")[0]))
    return checks


def network_checks(settings: Settings) -> list[Check]:
    """OAuth-only. Proves app authentication, nothing about sellers or buyers."""
    if settings.paypal_mode != "sandbox" or not (
        _configured(settings.paypal_client_id) and _configured(settings.paypal_client_secret)
    ):
        return [Check("paypal_oauth", NOT_RUN, "sandbox credentials not configured")]

    import httpx

    try:
        with httpx.Client(base_url=settings.paypal_base_url, timeout=settings.paypal_timeout_seconds) as client:
            resp = client.post(
                "/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(settings.paypal_client_id, settings.paypal_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        # Report the exception *type* only; a message can echo a URL.
        return [Check("paypal_oauth", "FAILED", f"transport error: {type(exc).__name__}")]

    if resp.status_code == 200:
        body = resp.json()
        scope_count = len(str(body.get("scope", "")).split())
        return [
            Check(
                "paypal_oauth",
                "AUTHENTICATED",
                f"http {resp.status_code}, {scope_count} scope(s), token not stored",
            )
        ]
    return [Check("paypal_oauth", "FAILED", f"http {resp.status_code}")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Secrets-safe SlotSaver capability preflight")
    parser.add_argument("--network", action="store_true", help="also perform an OAuth-only check")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        settings = load_settings(strict=False)
    except ConfigError as exc:
        # ConfigError messages are authored by us and contain no values.
        print(f"configuration: INVALID ({exc})", file=sys.stderr)
        return 2

    checks = static_checks(settings)
    if args.network:
        checks.extend(network_checks(settings))

    if args.json:
        print(json.dumps([c.__dict__ for c in checks], indent=2))
    else:
        print(f"SlotSaver preflight — mode={settings.paypal_mode}")
        for check in checks:
            print(f"  {check.render()}")

    blocking = [c for c in checks if c.status in {MISSING, UNSUPPORTED, "FAILED"}]
    if blocking and settings.paypal_mode == "sandbox":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
