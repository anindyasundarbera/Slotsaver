from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import assistant_dep, customer_session, demo_day, get_db, settings_dep
from ..models import AuthSession
from ..schemas import AssistantMessage, AssistantReply
from ..security import limiter
from ..services.assistant import Assistant

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/message", response_model=AssistantReply)
def post_message(
    payload: AssistantMessage,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    assistant: Assistant = Depends(assistant_dep),
    session: AuthSession = Depends(customer_session),
) -> AssistantReply:
    limiter.assistant.check(f"assistant:{session.user_id}")
    day = demo_day(db, settings)
    reply = assistant.run(db, session.user, payload.message, day)
    db.commit()
    return reply
