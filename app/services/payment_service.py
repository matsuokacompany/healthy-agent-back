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

from app.core.config import settings
from app.db.security_context import set_database_service_context
from app.models.models import Subscription, SubscriptionStatusEnum, User

logger = logging.getLogger(__name__)

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

    def start_checkout(self, user: User) -> dict[str, Any]:
        """Create (or reuse) the Asaas customer + subscription and return a payment link."""
        if not settings.ASAAS_SELF_MONITORING_PRICE_CENTS:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SELF_MONITORING_BILLING_NOT_CONFIGURED",
            )
        if not user.cpf:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CPF_REQUIRED_FOR_BILLING",
            )

        subscription = self.get_or_create_subscription_record(user)

        if not subscription.provider_customer_id:
            subscription.provider_customer_id = self._create_customer(user)
            self.db.commit()

        if subscription.provider_subscription_id and subscription.status != SubscriptionStatusEnum.CANCELED.value:
            invoice_url = self._fetch_latest_invoice_url(subscription.provider_subscription_id)
        else:
            asaas_subscription = self._create_subscription(subscription.provider_customer_id)
            subscription.provider_subscription_id = asaas_subscription["id"]
            self.db.commit()
            invoice_url = asaas_subscription.get("invoiceUrl") or self._fetch_latest_invoice_url(
                asaas_subscription["id"]
            )

        return {"checkout_url": invoice_url, "status": subscription.status}

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

    def _create_subscription(self, customer_id: str) -> dict[str, Any]:
        value = round(settings.ASAAS_SELF_MONITORING_PRICE_CENTS / 100, 2)
        next_due_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{_asaas_base_url()}/subscriptions",
                headers=_asaas_headers(),
                json={
                    "customer": customer_id,
                    # UNDEFINED lets the customer pick PIX/boleto/card on
                    # Asaas's hosted invoice page instead of us collecting it.
                    "billingType": "UNDEFINED",
                    "cycle": "MONTHLY",
                    "value": value,
                    "nextDueDate": next_due_date,
                    "description": "Julha - Automonitoramento de sintomas",
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
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{_asaas_base_url()}/payments",
                headers=_asaas_headers(),
                params={"subscription": asaas_subscription_id, "limit": 1},
            )
        if response.status_code >= 400:
            return None
        payments = response.json().get("data") or []
        return payments[0].get("invoiceUrl") if payments else None

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

    def is_active(self, user: User) -> bool:
        subscription = self.db.query(Subscription).filter(Subscription.user_id == user.id).first()
        return bool(subscription and subscription.status == SubscriptionStatusEnum.ACTIVE.value)
