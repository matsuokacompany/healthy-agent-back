import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.models.models import User
from app.models.schemas import SelfMonitoringCheckoutResponse
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Billing"])
webhook_router = APIRouter(tags=["Billing"])


@router.post("/subscription", response_model=SelfMonitoringCheckoutResponse)
@limiter.limit("5/minute")
def create_self_monitoring_checkout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PaymentService(db).start_checkout(current_user)


@webhook_router.post("/webhook/asaas", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("120/minute")
async def asaas_webhook(
    request: Request,
    db: Session = Depends(get_db),
    # Asaas echoes back the token you set in its dashboard (Configurações >
    # Integrações > Webhooks) as an "asaas-access-token" header — confirm the
    # exact header name on that screen once the webhook is registered; this
    # fails closed (403) if it's wrong, so it won't silently accept forged
    # requests, but it also won't work until the name is verified.
    asaas_access_token: str | None = Header(default=None),
):
    configured_token = settings.ASAAS_WEBHOOK_TOKEN
    if not configured_token:
        logger.error("ASAAS_WEBHOOK_TOKEN not configured; rejecting webhook")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="asaas_webhook_not_configured")
    if not asaas_access_token or not hmac.compare_digest(asaas_access_token, configured_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook token")

    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    PaymentService(db).handle_webhook_event(payload)
    return None
