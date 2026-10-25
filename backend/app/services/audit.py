from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import AuditEvent

REDACT_KEYS = {
    "authorization",
    "access_token",
    "client_secret",
    "token",
    "cookie",
    "csrf",
    "card",
    "cvv",
    "api_key",
    "password",
}


def redact(payload: dict) -> dict:
    clean: dict = {}
    for key, value in payload.items():
        if any(marker in key.lower() for marker in REDACT_KEYS):
            clean[key] = "[redacted]"
        elif isinstance(value, dict):
            clean[key] = redact(value)
        else:
            clean[key] = value
    return clean


def record(
    db: Session,
    *,
    action: str,
    actor_id: str = "",
    actor_role: str = "",
    subject_type: str = "",
    subject_id: str = "",
    detail: dict | None = None,
    correlation_id: str = "",
) -> AuditEvent:
    event = AuditEvent(
        at=utcnow(),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        detail=redact(detail or {}),
        correlation_id=correlation_id,
    )
    db.add(event)
    return event
