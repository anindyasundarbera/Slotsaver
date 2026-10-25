from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import demo_day, get_db, settings_dep
from ..models import Service, Technician
from ..schemas import ConfigOut, DemoUser, HealthOut, ServiceOut, TechnicianOut
from ..seed import DEMO_USERS
from ..timeutil import tz_label
from ..db import utcnow

router = APIRouter(prefix="/api", tags=["meta"])

VERSION = "1.0.0"


@router.get("/config", response_model=ConfigOut)
def config(
    db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)
) -> ConfigOut:
    day = demo_day(db, settings)
    at = utcnow().astimezone(settings.tz)
    return ConfigOut(
        business_name=settings.business_name,
        timezone=settings.business_tz,
        timezone_label=tz_label(settings.tz, at),
        currency=settings.currency,
        demo_date=day,
        hold_ttl_minutes=settings.hold_ttl_minutes,
        paypal_mode=settings.paypal_mode,
        assistant_mode=settings.assistant_mode,
        demo_users=[
            DemoUser(email=email, display_name=name, role=role, hint=role.capitalize())
            for email, name, role in DEMO_USERS
        ],
        supports_webhooks=settings.paypal_mode == "sandbox" and settings.paypal_webhooks_enabled,
    )


@router.get("/services", response_model=list[ServiceOut])
def services(db: Session = Depends(get_db)) -> list[ServiceOut]:
    rows = db.execute(select(Service).order_by(Service.price_cents)).scalars().all()
    return [
        ServiceOut(
            id=s.id,
            code=s.code,
            name=s.name,
            duration_minutes=s.duration_minutes,
            price_cents=s.price_cents,
            currency=s.currency,
            required_skill=s.required_skill,
            description=s.description,
        )
        for s in rows
    ]


@router.get("/technicians", response_model=list[TechnicianOut])
def technicians(db: Session = Depends(get_db)) -> list[TechnicianOut]:
    rows = db.execute(
        select(Technician).where(Technician.active.is_(True)).order_by(Technician.name)
    ).scalars().all()
    return [
        TechnicianOut(
            id=t.id, name=t.name, initials=t.initials, skills=t.skills or [], color=t.color
        )
        for t in rows
    ]


@router.get("/health", response_model=HealthOut)
def health(
    db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)
) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    day = demo_day(db, settings) if db_ok else settings.demo_date
    return HealthOut(
        status="ok" if db_ok else "degraded",
        database="ok" if db_ok else "unavailable",
        paypal_mode=settings.paypal_mode,
        assistant_mode=settings.assistant_mode,
        demo_date=day,
        version=VERSION,
    )
