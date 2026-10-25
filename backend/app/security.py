from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .errors import Forbidden, RateLimited, Unauthorized
from .models import AuthSession, User

SESSION_COOKIE = "ss_session"
CSRF_COOKIE = "ss_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_session(db: Session, settings: Settings, user: User) -> tuple[AuthSession, str]:
    token = new_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_token(),
        created_at=utcnow(),
        expires_at=utcnow() + __import__("datetime").timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.flush()
    return session, token


def resolve_session(db: Session, token: str | None) -> AuthSession | None:
    if not token:
        return None
    row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at <= utcnow():
        return None
    return row


def require_session(db: Session, token: str | None) -> AuthSession:
    session = resolve_session(db, token)
    if session is None:
        raise Unauthorized()
    return session


def require_owner(session: AuthSession) -> AuthSession:
    if session.user.role != "owner":
        raise Forbidden("Only the business owner can perform this action.")
    return session


def require_customer(session: AuthSession) -> AuthSession:
    if session.user.role != "customer":
        raise Forbidden("Only a customer account can perform this action.")
    return session


def check_csrf(request: Request, settings: Settings) -> None:
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER)
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise Forbidden("Missing or invalid CSRF token.")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.app_origin.rstrip("/"):
        # Same-origin requests from the packaged app are allowed; cross-origin are not.
        raise Forbidden("Cross-origin request rejected.")


@dataclass
class Bucket:
    limit: int
    window_seconds: float
    hits: dict[str, deque] = field(default_factory=dict)

    def check(self, key: str) -> None:
        now = time.monotonic()
        entries = self.hits.setdefault(key, deque())
        while entries and now - entries[0] > self.window_seconds:
            entries.popleft()
        if len(entries) >= self.limit:
            retry = int(self.window_seconds - (now - entries[0])) + 1
            raise RateLimited(f"Too many requests. Retry in about {retry}s.")
        entries.append(now)


class Limiter:
    def __init__(self) -> None:
        self.login = Bucket(limit=10, window_seconds=60)
        self.assistant = Bucket(limit=20, window_seconds=60)
        self.payment = Bucket(limit=15, window_seconds=60)

    def reset(self) -> None:
        self.login.hits.clear()
        self.assistant.hits.clear()
        self.payment.hits.clear()


limiter = Limiter()


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
