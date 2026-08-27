"""Self-service (B2C) subscription billing via Asaas.

Written from Asaas's documented v3 REST API shape, not yet verified against a
live sandbox (no credentials were available while writing this). Before
relying on this in production, smoke-test with a real ASAAS_API_KEY and
confirm against the current Asaas docs:

- the exact webhook `event` names Asaas sends for subscription payments
  (PAYMENT_CONFIRMED/PAYMENT_RECEIVED/PAYMENT_OVERDUE/etc. below is a
  best-effort list, not a verified one);
- the response shape of GET /v3/payments (assumed to be
  {"data": [...], ...}, used only as a fallback to fetch the invoice URL).

Never used for professional-managed patients: their billing is a separate
business arrangement between Julha and the clinic, outside this platform.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.billing_plans import SelfMonitoringPlan, get_professional_plan, get_self_monitoring_plan
from app.core.config import settings
from app.core.permissions import has_role
from app.db.security_context import set_database_service_context
from app.models.models import ProfessionalProfile, RoleNameEnum, Subscription, SubscriptionStatusEnum, User

logger = logging.getLogger(__name__)


def subscription_grants_access(subscription: Subscription | None) -> bool:
    """Whether a subscription currently entitles its user to self-monitoring.

    Computed live from trial_ends_at rather than a stored "expired" status,
    so there's no cron job needed to flip state exactly when a trial lapses.
    """
    if not subscription:
        return False
    if subscription.status == SubscriptionStatusEnum.ACTIVE.value:
        if subscription.cancel_at_period_end and subscription.current_period_end:
            current_period_end = subscription.current_period_end
            if current_period_end.tzinfo is None:
                current_period_end = current_period_end.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) < current_period_end
        return True
    if subscription.status == SubscriptionStatusEnum.TRIALING.value:
        trial_ends_at = subscription.trial_ends_at
        if not trial_ends_at:
            return False
        # SQLite (tests) drops tzinfo on round-trip even for DateTime(timezone=True)
        # columns; every value we write here is UTC, so treat a naive read-back as UTC.
        if trial_ends_at.tzinfo is None:
            trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < trial_ends_at
    return False


def professional_has_access(profile: ProfessionalProfile, subscription: Subscription | None) -> bool:
    """Whether a professional currently has full (unlocked) platform access.

    True while inside their grandfathered/grace `free_until` window, or while
    their own Subscription grants access (same rule as patients — see
    subscription_grants_access). Professionals never get a TRIALING
    subscription today (nothing calls start_trial_if_needed for them), so in
    practice this resolves to "grace period, or ACTIVE subscription".
    """
    if profile.free_until is not None and datetime.now(timezone.utc).date() <= profile.free_until:
        return True
    return subscription_grants_access(subscription)

# CDC art. 49 -- consumer's unconditional right of withdrawal for contracts
# made online, counted from the first payment (see Política de Reembolso §1).
REFUND_WINDOW_DAYS = 7

ASAAS_BASE_URLS = {
    "sandbox": "https://sandbox.asaas.com/api/v3",
    "production": "https://api.asaas.com/v3",
}


def _asaas_base_url() -> str:
    return ASAAS_BASE_URLS.get(settings.ASAAS_ENV, ASAAS_BASE_URLS["sandbox"])


def _asaas_headers() -> dict[str, str]:
    if not settings.ASAAS_API_KEY:
        raise RuntimeError("ASAAS_API_KEY must be configured for billing operations")
    return {"access_token": settings.ASAAS_API_KEY, "Content-Type": "application/json"}


class PaymentService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_subscription_record(self, user: User) -> Subscription:
        existing = self.db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if existing:
            return existing
        subscription = Subscription(user_id=user.id, status=SubscriptionStatusEnum.PENDING.value)
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def start_trial_if_needed(self, user: User) -> Subscription:
        """Start the free trial the moment a patient begins self-monitoring.

        Only flips a freshly-created PENDING record (no trial_ends_at yet) to
        TRIALING — a no-op for anyone already TRIALING/ACTIVE/PAST_DUE/
        CANCELED, so this is safe to call every time create_or_reactivate_plan
        runs, not just the first time.
        """
        subscription = self.get_or_create_subscription_record(user)
        if subscription.status == SubscriptionStatusEnum.PENDING.value and not subscription.trial_ends_at:
            subscription.status = SubscriptionStatusEnum.TRIALING.value
            subscription.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=settings.ASAAS_SELF_MONITORING_TRIAL_DAYS)
            self.db.commit()
            self.db.refresh(subscription)
        return subscription

    def has_access(self, user: User) -> bool:
        subscription = self.db.query(Subscription).filter(Subscription.user_id == user.id).first()
        return subscription_grants_access(subscription)

    def has_professional_access(self, profile: ProfessionalProfile) -> bool:
        subscription = self.db.query(Subscription).filter(Subscription.user_id == profile.user_id).first()
        return professional_has_access(profile, subscription)

    def start_checkout(self, user: User, plan_id: str) -> dict[str, Any]:
        """Create (or reuse) the Asaas customer + subscription and return a payment link.

        Which catalog is offered (patient self-monitoring vs. professional)
        is derived from the caller's own role — never a client-supplied flag
        — so a patient can never buy a professional plan or vice versa.
        """
        is_professional_plan = has_role(user, RoleNameEnum.PROFESSIONAL)
        plan = (get_professional_plan if is_professional_plan else get_self_monitoring_plan)(plan_id)
        if not plan:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_PLAN")
        if not user.cpf:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CPF_REQUIRED_FOR_BILLING",
            )

        subscription = self.get_or_create_subscription_record(user)

        if subscription.status == SubscriptionStatusEnum.ACTIVE.value and subscription.plan_id != plan.id:
            # Changing plans on an already-paying subscriber isn't supported
            # yet — that needs cancel-then-resubscribe handling on the Asaas
            # side to avoid double-charging. Keep this explicit rather than
            # silently ignoring the requested plan.
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PLAN_CHANGE_NOT_SUPPORTED")

        if not subscription.provider_customer_id:
            subscription.provider_customer_id = self._create_customer(user)
            self.db.commit()

        reuse_existing = (
            subscription.provider_subscription_id
            and subscription.status != SubscriptionStatusEnum.CANCELED.value
            and subscription.plan_id == plan.id
        )
        if reuse_existing:
            if subscription.cancel_at_period_end:
                # Checking out again for the same plan they'd previously
                # canceled reads as "I changed my mind" -- undo the
                # cancel-at-period-end instead of leaving it pending.
                subscription.cancel_at_period_end = False
                self.db.commit()
            invoice_url = self._fetch_latest_invoice_url(subscription.provider_subscription_id)
        else:
            asaas_subscription = self._create_subscription(
                subscription.provider_customer_id, plan, professional=is_professional_plan
            )
            subscription.provider_subscription_id = asaas_subscription["id"]
            subscription.plan_id = plan.id
            self.db.commit()
            invoice_url = asaas_subscription.get("invoiceUrl") or self._fetch_latest_invoice_url(
                asaas_subscription["id"]
            )

        return {"checkout_url": invoice_url, "status": subscription.status, "plan_id": plan.id}

    def cancel_subscription(self, user: User) -> Subscription:
        """Stop future renewals; access is kept until current_period_end,
        matching the "cancelamento a qualquer momento, com efeitos a partir
        do próximo ciclo" promised in Termos de Uso §8.2.c."""
        subscription = self.get_or_create_subscription_record(user)
        if subscription.status != SubscriptionStatusEnum.ACTIVE.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="NO_ACTIVE_SUBSCRIPTION")
        if subscription.cancel_at_period_end:
            return subscription
        if subscription.provider_subscription_id:
            self._delete_asaas_subscription(subscription.provider_subscription_id)
        subscription.cancel_at_period_end = True
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def refund_subscription(self, user: User) -> Subscription:
        """Full refund of the most recent payment, only inside the CDC art.
        49 withdrawal window (Política de Reembolso §1) -- 7 days from the
        first successful payment, not from signup."""
        subscription = self.get_or_create_subscription_record(user)
        first_paid_at = subscription.first_paid_at
        if not first_paid_at or not subscription.provider_subscription_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="NO_PAYMENT_TO_REFUND")
        if first_paid_at.tzinfo is None:
            first_paid_at = first_paid_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - first_paid_at > timedelta(days=REFUND_WINDOW_DAYS):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="REFUND_WINDOW_EXPIRED")

        payment = self._fetch_latest_payment(subscription.provider_subscription_id)
        if not payment or payment.get("status") not in {"CONFIRMED", "RECEIVED"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="NO_PAYMENT_TO_REFUND")

        self._refund_payment(payment["id"])
        self._delete_asaas_subscription(subscription.provider_subscription_id)
        subscription.status = SubscriptionStatusEnum.CANCELED.value
        subscription.cancel_at_period_end = False
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def _create_customer(self, user: User) -> str:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{_asaas_base_url()}/customers",
                headers=_asaas_headers(),
                json={
                    "name": user.name,
                    "email": user.email,
                    "cpfCnpj": user.cpf,
                    "phone": user.phone,
                    "externalReference": str(user.id),
                },
            )
        if response.status_code >= 400:
            logger.error("Asaas customer creation failed | user_id=%s status=%s", user.id, response.status_code)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="BILLING_PROVIDER_ERROR")
        return response.json()["id"]

    def _create_subscription(
        self, customer_id: str, plan: SelfMonitoringPlan, *, professional: bool = False
    ) -> dict[str, Any]:
        value = round(plan.price_cents / 100, 2)
        next_due_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        description = (
            f"Julha - Assinatura profissional ({plan.label})"
            if professional
            else f"Julha - Automonitoramento de sintomas ({plan.label})"
        )
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{_asaas_base_url()}/subscriptions",
                headers=_asaas_headers(),
                json={
                    "customer": customer_id,
                    # UNDEFINED lets the customer pick PIX/boleto/card on
                    # Asaas's hosted invoice page instead of us collecting it.
                    "billingType": "UNDEFINED",
                    "cycle": plan.cycle,
                    "value": value,
                    "nextDueDate": next_due_date,
                    "description": description,
                },
            )
        if response.status_code >= 400:
            logger.error(
                "Asaas subscription creation failed | customer_id=%s status=%s",
                customer_id,
                response.status_code,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="BILLING_PROVIDER_ERROR")
        return response.json()

    def _fetch_latest_invoice_url(self, asaas_subscription_id: str) -> str | None:
        payment = self._fetch_latest_payment(asaas_subscription_id)
        return payment.get("invoiceUrl") if payment else None

    def _fetch_latest_payment(self, asaas_subscription_id: str) -> dict[str, Any] | None:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{_asaas_base_url()}/payments",
                headers=_asaas_headers(),
                params={"subscription": asaas_subscription_id, "limit": 1},
            )
        if response.status_code >= 400:
            return None
        payments = response.json().get("data") or []
        return payments[0] if payments else None

    def _delete_asaas_subscription(self, asaas_subscription_id: str) -> None:
        with httpx.Client(timeout=10.0) as client:
            response = client.delete(
                f"{_asaas_base_url()}/subscriptions/{asaas_subscription_id}",
                headers=_asaas_headers(),
            )
        if response.status_code >= 400:
            logger.error(
                "Asaas subscription cancellation failed | subscription_id=%s status=%s",
                asaas_subscription_id,
                response.status_code,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="BILLING_PROVIDER_ERROR")

    def _refund_payment(self, asaas_payment_id: str) -> None:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{_asaas_base_url()}/payments/{asaas_payment_id}/refund",
                headers=_asaas_headers(),
            )
        if response.status_code >= 400:
            logger.error(
                "Asaas payment refund failed | payment_id=%s status=%s",
                asaas_payment_id,
                response.status_code,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="BILLING_PROVIDER_ERROR")

    def handle_webhook_event(self, payload: dict[str, Any]) -> None:
        set_database_service_context(self.db, "asaas_webhook")

        event = payload.get("event")
        payment = payload.get("payment") or {}
        asaas_subscription_id = payment.get("subscription")
        if not asaas_subscription_id:
            logger.info("Ignoring Asaas webhook with no subscription reference | event=%s", event)
            return

        subscription = (
            self.db.query(Subscription)
            .filter(Subscription.provider_subscription_id == asaas_subscription_id)
            .first()
        )
        if not subscription:
            logger.warning(
                "Asaas webhook for unknown subscription | asaas_subscription_id=%s event=%s",
                asaas_subscription_id,
                event,
            )
            return

        if event in {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}:
            subscription.status = SubscriptionStatusEnum.ACTIVE.value
            if subscription.first_paid_at is None:
                subscription.first_paid_at = datetime.now(timezone.utc)
            due_date = payment.get("dueDate")
            if due_date:
                subscription.current_period_end = datetime.fromisoformat(due_date).replace(tzinfo=timezone.utc)
        elif event == "PAYMENT_OVERDUE":
            subscription.status = SubscriptionStatusEnum.PAST_DUE.value
        elif event in {"PAYMENT_DELETED", "PAYMENT_REFUNDED", "SUBSCRIPTION_DELETED"}:
            subscription.status = SubscriptionStatusEnum.CANCELED.value
        else:
            logger.info("Unhandled Asaas webhook event | event=%s", event)
            return

        self.db.commit()
