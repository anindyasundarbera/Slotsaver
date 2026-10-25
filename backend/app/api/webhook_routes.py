from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_db, provider_dep, settings_dep
from ..services.bookings import handle_payment_event
from ..services.payments import PaymentProvider

log = logging.getLogger("slotsaver.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/paypal")
async def paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    provider: PaymentProvider = Depends(provider_dep),
) -> Response:
    if not settings.paypal_webhooks_enabled:
        # Intake is not registered. Refuse rather than pretend, and never skip
        # signature verification just because the feature is off.
        return Response(
            status_code=503,
            content=b'{"error":{"code":"WEBHOOKS_DISABLED","message":"Webhook intake is not enabled."}}',
            media_type="application/json",
        )

    body = await request.body()
    if len(body) > 200_000:
        return Response(status_code=413)
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        return Response(status_code=400)

    event_id = str(event.get("id") or "")[:64]
    event_type = str(event.get("event_type") or "")[:64]
    if not event_id:
        return Response(status_code=400)

    verified = provider.verify_webhook(headers, body)
    if not verified:
        log.warning("webhook rejected: signature verification failed event_id=%s", event_id)
        return Response(status_code=401)

    result = handle_payment_event(
        db,
        settings,
        provider,
        event=event,
        event_id=event_id,
        signature_verified=True,
        event_type=event_type,
        correlation_id=getattr(request.state, "correlation_id", ""),
    )
    db.commit()
    log.info("webhook %s outcome=%s", event_type, result)
    return Response(status_code=200)
