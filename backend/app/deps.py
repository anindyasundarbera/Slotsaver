from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import make_session_factory, get_engine
from .errors import Unauthorized
from .models import AuthSession, DemoClock, User
from .security import SESSION_COOKIE, check_csrf, client_key, limiter, require_session
from .services.assistant import Assistant
from .services.payments import PaymentProvider, build_provider
from .services.payments import SimulatedProvider

_SESSION_FACTORY = None


def _factory():
    global _SESSION_FACTORY
    engine = get_engine(get_settings().database_url)
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = make_session_factory(engine)
    return _SESSION_FACTORY


def reset_factory() -> None:
    global _SESSION_FACTORY, _PROVIDER
    _SESSION_FACTORY = None
    _PROVIDER = None


_PROVIDER: PaymentProvider | None = None


def get_db(request: Request) -> Iterator[Session]:
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def settings_dep(settings: Settings = Depends(get_settings)) -> Settings:
    """Resolve through FastAPI so dependency overrides reach every route."""
    return settings


def db_session(request: Request) -> Session:
    return _factory()()


def demo_day(db: Session, settings: Settings) -> date:
    row = db.get(DemoClock, 1)
    if row is None:
        return settings.demo_date
    try:
        return date.fromisoformat(row.demo_date)
    except ValueError:
        return settings.demo_date


def provider_dep(settings: Settings = Depends(settings_dep)) -> PaymentProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = build_provider(settings)
    return _PROVIDER


def assistant_dep(settings: Settings = Depends(settings_dep)) -> Assistant:
    return Assistant(settings)


def current_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> AuthSession:
    check_csrf(request, settings)
    token = request.cookies.get(SESSION_COOKIE)
    session = require_session(db, token)
    return session


def current_user(session: AuthSession = Depends(current_session)) -> User:
    return session.user


def owner_session(session: AuthSession = Depends(current_session)) -> AuthSession:
    from .security import require_owner

    return require_owner(session)


def customer_session(session: AuthSession = Depends(current_session)) -> AuthSession:
    from .security import require_customer

    return require_customer(session)


def limit(key: str, request: Request, bucket) -> None:
    bucket.check(f"{key}:{client_key(request)}")
