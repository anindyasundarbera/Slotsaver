from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
# Documented API host plus its legacy alias. Both are the *API*; the bare
# `sandbox.paypal.com` is the buyer-facing web host and is not an API origin.
ALLOWED_PAYPAL_ORIGINS = {
    SANDBOX_BASE_URL,
    "https://api.sandbox.paypal.com",
}
# Hosts people commonly confuse with the API origin, for a useful error message.
MISCONFIGURED_PAYPAL_HOSTS = {
    "https://sandbox.paypal.com": "that is PayPal's buyer-facing web host, not the API",
    "https://www.sandbox.paypal.com": "that is the checkout page host, not the API",
    "https://api-m.paypal.com": "that is LIVE PayPal; this POC refuses live mode",
    "https://api.paypal.com": "that is LIVE PayPal; this POC refuses live mode",
}


def _load_dotenv_once() -> bool:
    """Populate os.environ from backend/.env, honouring existing variables.

    Never overrides a real environment variable, so shells, CI and the test
    harness always win over the file. Returns True when a file was read.
    """
    if os.environ.get("SLOTSAVER_SKIP_DOTENV", "") == "1":
        return False
    if not ENV_FILE.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:  # pragma: no cover - dependency is pinned
        return False
    # override=False: an exported variable beats the file.
    return load_dotenv(dotenv_path=ENV_FILE, override=False)


DOTENV_LOADED = _load_dotenv_once()


class ConfigError(RuntimeError):
    pass




def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - startup misconfiguration
        raise ConfigError(f"{name} must be an integer") from exc





PLACEHOLDER_MARKERS = ("your_", "your-", "replace", "changeme", "example", "demo-", "todo")


def is_placeholder(value: str | None) -> bool:
    """True for blank or obviously fake values; used to refuse fake credentials."""
    if value is None:
        return True
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "SlotSaver"
    environment: str = "development"
    database_url: str = "sqlite:///./data/slotsaver.db"
    business_tz: str = "America/New_York"
    business_name: str = "Northline Appliance Care"
    currency: str = "USD"
    demo_date: date = date(2026, 11, 3)
    hold_ttl_minutes: int = 15
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    app_origin: str = "http://localhost:4200"
    seed_demo_data: bool = True
    allow_demo_reset: bool = True

    # PayPal. "simulated" is a clearly labelled offline substitute, never payment evidence.
    paypal_mode: str = "simulated"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_merchant_id: str = ""
    paypal_webhook_id: str = ""
    simulated_webhook_secret: str = ""
    simulated_webhook_secret_generated: bool = False
    paypal_timeout_seconds: int = 20
    paypal_base_url_override: str = ""
    paypal_return_url: str = ""
    paypal_cancel_url: str = ""
    paypal_webhooks_enabled: bool = False
    paypal_webhook_url: str = ""
    enable_bryntum: bool = True

    # Assistant. "scripted" is the deterministic offline runtime; "llm" calls an
    # OpenAI-compatible chat endpoint.
    assistant_mode: str = "scripted"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_timeout_seconds: int = 20
    llm_max_tool_iterations: int = 4

    secrets: tuple[str, ...] = field(default_factory=tuple)
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.business_tz)

    @property
    def paypal_webhook_url_effective(self) -> str:
        """Public intake URL, defaulting to the configured app origin."""
        if self.paypal_webhook_url:
            return self.paypal_webhook_url
        return f"{self.app_origin.rstrip('/')}/api/webhooks/paypal"

    @property
    def paypal_base_url(self) -> str:
        """Always an allowed API origin; the legacy alias is normalised."""
        return SANDBOX_BASE_URL

    def local(self, dt: datetime) -> datetime:
        return dt.astimezone(self.tz)


def load_settings(*, strict: bool = True) -> Settings:
    mode = (_env("PAYPAL_MODE", "simulated") or "simulated").lower()
    if mode not in {"simulated", "sandbox"}:
        raise ConfigError(
            f"PAYPAL_MODE={mode!r} is not supported. This POC refuses live payment mode "
            "and only allows 'simulated' or 'sandbox'."
        )
    assistant = (_env("ASSISTANT_MODE", "scripted") or "scripted").lower()
    if assistant not in {"scripted", "llm"}:
        raise ConfigError(f"ASSISTANT_MODE={assistant!r} must be 'scripted' or 'llm'")

    app_origin = _env("APP_ORIGIN", "http://localhost:4200") or "http://localhost:4200"
    demo_raw = _env("DEMO_DATE", "2026-11-03") or "2026-11-03"
    try:
        demo_date = date.fromisoformat(demo_raw)
    except ValueError as exc:
        raise ConfigError("DEMO_DATE must be an ISO date (YYYY-MM-DD)") from exc

    client_secret = _env("PAYPAL_CLIENT_SECRET", "") or ""
    llm_key = _env("LLM_API_KEY", "") or ""
    secrets = tuple(s for s in (client_secret, llm_key, _env("SIMULATED_WEBHOOK_SECRET", "")) if s)

    settings = Settings(
        environment=_env("ENVIRONMENT", "development") or "development",
        database_url=_env("DATABASE_URL", "sqlite:///./data/slotsaver.db") or "sqlite:///./data/slotsaver.db",
        business_tz=_env("BUSINESS_TZ", "America/New_York") or "America/New_York",
        business_name=_env("BUSINESS_NAME", "Northline Appliance Care") or "Northline Appliance Care",
        demo_date=demo_date,
        hold_ttl_minutes=_env_int("HOLD_TTL_MINUTES", 15),
        session_ttl_hours=_env_int("SESSION_TTL_HOURS", 12),
        cookie_secure=_env_bool("COOKIE_SECURE", False),
        app_origin=app_origin,
        seed_demo_data=_env_bool("SEED_DEMO_DATA", True),
        allow_demo_reset=_env_bool("ALLOW_DEMO_RESET", True),
        paypal_mode=mode,
        paypal_client_id=_env("PAYPAL_CLIENT_ID", "") or "",
        paypal_client_secret=client_secret,
        paypal_merchant_id=_env("PAYPAL_MERCHANT_ID", "") or "",
        paypal_webhook_id=_env("PAYPAL_WEBHOOK_ID", "") or "",
        simulated_webhook_secret=_env("SIMULATED_WEBHOOK_SECRET", "") or "",
        paypal_timeout_seconds=_env_int(
            "PAYPAL_TIMEOUT_SECONDS", _env_int("PAYPAL_HTTP_TIMEOUT_SECONDS", 20)
        ),
        paypal_base_url_override=_env("PAYPAL_BASE_URL", "") or "",
        paypal_return_url=_env("PAYPAL_RETURN_URL", "") or "",
        paypal_cancel_url=_env("PAYPAL_CANCEL_URL", "") or "",
        paypal_webhook_url=_env("PAYPAL_WEBHOOK_URL", "") or "",
        paypal_webhooks_enabled=_env_bool(
            "PAYPAL_WEBHOOKS_ENABLED",
            bool(_env("PAYPAL_WEBHOOK_ID", "")),
        ),
        enable_bryntum=_env_bool("SLOTSAVER_ENABLE_BRYNTUM", True),
        assistant_mode=assistant,
        llm_base_url=_env("LLM_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1",
        llm_model=_env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        llm_api_key=llm_key,
        llm_timeout_seconds=_env_int("LLM_TIMEOUT_SECONDS", 20),
        llm_max_tool_iterations=_env_int("LLM_MAX_TOOL_ITERATIONS", 4),
        secrets=secrets,
    )
    # A webhook HMAC key that ships in the repo is not a control. Refuse
    # placeholders and never fall back to a published literal: if the operator
    # did not configure one, use a random per-process value so no third party can
    # mint a "verified" capture. (Alert: independent security review, finding 1.)
    if settings.paypal_mode == "simulated":
        if is_placeholder(settings.simulated_webhook_secret):
            import secrets as _secrets

            settings = replace(
                settings,
                simulated_webhook_secret=_secrets.token_urlsafe(32),
                simulated_webhook_secret_generated=True,
            )

    if (
        strict
        and settings.paypal_mode == "sandbox"
        and (is_placeholder(settings.paypal_client_id) or is_placeholder(settings.paypal_client_secret))
    ):
        raise ConfigError("PAYPAL_MODE=sandbox requires PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET")
    if settings.paypal_base_url_override:
        origin = settings.paypal_base_url_override.strip().rstrip("/")
        if origin in MISCONFIGURED_PAYPAL_HOSTS:
            raise ConfigError(
                f"PAYPAL_BASE_URL={origin!r} is wrong: "
                f"{MISCONFIGURED_PAYPAL_HOSTS[origin]}. "
                f"Leave PAYPAL_BASE_URL blank, or set it to {SANDBOX_BASE_URL}."
            )
        if origin not in ALLOWED_PAYPAL_ORIGINS:
            raise ConfigError(
                "PAYPAL_BASE_URL must be the approved sandbox API origin "
                f"({SANDBOX_BASE_URL}); live or unknown hosts are refused by this POC. "
                "Leave it blank to use the default."
            )
    for name, value in (
        ("PAYPAL_RETURN_URL", settings.paypal_return_url),
        ("PAYPAL_CANCEL_URL", settings.paypal_cancel_url),
    ):
        if value and not value.startswith(("http://localhost", "https://")):
            raise ConfigError(f"{name} must be an http(s) URL")

    if strict and settings.assistant_mode == "llm" and is_placeholder(settings.llm_api_key):
        raise ConfigError("ASSISTANT_MODE=llm requires LLM_API_KEY")
    if not app_origin.startswith(("http://", "https://")):
        raise ConfigError("APP_ORIGIN must be an absolute http(s) origin")
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()


BUSINESS_HOURS: dict[int, tuple[time, time]] = {}
