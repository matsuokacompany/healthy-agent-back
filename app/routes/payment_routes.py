import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.billing_plans import get_professional_plans, get_self_monitoring_plans
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.permissions import has_role
from app.core.rate_limit import limiter
from app.models.models import ProfessionalProfile, RoleNameEnum, Subscription, User
from app.models.schemas import (
    SelfMonitoringCheckoutRequest,
    SelfMonitoringCheckoutResponse,
    SelfMonitoringPlanRead,
    SelfMonitoringSubscriptionRead,
)
from app.services.payment_service import PaymentService
from app.services.professional_capacity_service import count_active_patients, resolve_patient_cap

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Billing"])
webhook_router = APIRouter(tags=["Billing"])


@router.get("/plans", response_model=list[SelfMonitoringPlanRead])
def list_self_monitoring_plans(current_user: User = Depends(get_current_user)):
    """Plan catalog for the caller's own billing — professionals see the
    professional catalog, patients see the self-monitoring catalog."""
    if has_role(current_user, RoleNameEnum.PROFESSIONAL):
        return get_professional_plans()
    return get_self_monitoring_plans()


def _subscription_response(db: Session, current_user: User, subscription: Subscription) -> SelfMonitoringSubscriptionRead:
    max_patients = None
    active_patient_count = None
    if has_role(current_user, RoleNameEnum.PROFESSIONAL):
        profile = db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == current_user.id).first()
        if profile:
            max_patients = resolve_patient_cap(db, profile)
            active_patient_count = count_active_patients(db, profile.id)
    return SelfMonitoringSubscriptionRead(
        status=subscription.status,
        current_period_end=subscription.current_period_end,
        trial_ends_at=subscription.trial_ends_at,
        plan_id=subscription.plan_id,
        cancel_at_period_end=subscription.cancel_at_period_end,
        first_paid_at=subscription.first_paid_at,
        max_patients=max_patients,
        active_patient_count=active_patient_count,
    )


@router.get("/subscription", response_model=SelfMonitoringSubscriptionRead)
def get_self_monitoring_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscription = PaymentService(db).get_or_create_subscription_record(current_user)
    return _subscription_response(db, current_user, subscription)


@router.post("/subscription", response_model=SelfMonitoringCheckoutResponse)
@limiter.limit("5/minute")
def create_self_monitoring_checkout(
    request: Request,
    payload: SelfMonitoringCheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PaymentService(db).start_checkout(current_user, payload.plan_id)


@router.post("/subscription/cancel", response_model=SelfMonitoringSubscriptionRead)
@limiter.limit("5/minute")
def cancel_self_monitoring_subscription(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscription = PaymentService(db).cancel_subscription(current_user)
    return _subscription_response(db, current_user, subscription)


@router.post("/subscription/refund", response_model=SelfMonitoringSubscriptionRead)
@limiter.limit("5/minute")
def refund_self_monitoring_subscription(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscription = PaymentService(db).refund_subscription(current_user)
    return _subscription_response(db, current_user, subscription)


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
