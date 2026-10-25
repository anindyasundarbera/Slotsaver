from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import current_session, demo_day, get_db, settings_dep
from ..errors import Unauthorized
from ..models import AuthSession, DemoClock, User
from ..schemas import DemoUser, LoginRequest, UserOut
from ..security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    check_csrf,
    client_key,
    create_session,
    limiter,
    resolve_session,
)
from ..seed import DEMO_USERS
from ..services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> UserOut:
    limiter.login.check(f"login:{client_key(request)}")
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None:
        raise Unauthorized("That email is not a demo account. Pick one from the sign-in list.")
    existing = request.cookies.get(SESSION_COOKIE)
    if existing:
        old = resolve_session(db, existing)
        if old is not None:
            old.revoked_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    session, token = create_session(db, settings, user)
    audit.record(
        db,
        action="auth.login",
        actor_id=user.id,
        actor_role=user.role,
        subject_type="user",
        subject_id=user.id,
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> dict:
    check_csrf(request, settings)
    token = request.cookies.get(SESSION_COOKIE)
    session = resolve_session(db, token)
    if session is not None:
        from ..db import utcnow

        session.revoked_at = utcnow()
        audit.record(
            db,
            action="auth.logout",
            actor_id=session.user_id,
            actor_role=session.user.role,
            subject_type="user",
            subject_id=session.user_id,
        )
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut | None)
def me(session: AuthSession = Depends(current_session)) -> UserOut | None:
    user = session.user
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role)
