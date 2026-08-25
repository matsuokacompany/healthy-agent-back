import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import Subscription, SubscriptionStatusEnum, User
from app.services.payment_service import PaymentService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_user(db, *, cpf="12345678900"):
    user = User(name="Paciente", email="paciente@example.com", phone="5511999990000", cpf=cpf)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsaasClient:
    """Stands in for httpx.Client, routing by URL suffix like the real Asaas API paths."""

    def __init__(self, *, customer_id="cus_123", subscription_id="sub_123", invoice_url="https://asaas.test/i/abc"):
        self.customer_id = customer_id
        self.subscription_id = subscription_id
        self.invoice_url = invoice_url
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        self.calls.append((url, json))
        if url.endswith("/customers"):
            assert json["cpfCnpj"], "cpfCnpj must be sent to Asaas"
            return FakeResponse(200, {"id": self.customer_id})
        if url.endswith("/subscriptions"):
            assert json["customer"] == self.customer_id
            return FakeResponse(200, {"id": self.subscription_id, "invoiceUrl": self.invoice_url})
        raise AssertionError(f"Unexpected POST {url}")

    def get(self, url, headers=None, params=None):
        self.calls.append((url, params))
        if url.endswith("/payments"):
            return FakeResponse(200, {"data": [{"invoiceUrl": self.invoice_url}]})
        raise AssertionError(f"Unexpected GET {url}")


@pytest.fixture(autouse=True)
def asaas_settings(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASAAS_ENV", "sandbox")
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", 2990)
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", "shared-secret")


def test_start_checkout_requires_price_configured(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", None)
    db = build_session()
    user = create_user(db)

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).start_checkout(user)

    assert exc.value.status_code == 503


def test_start_checkout_requires_cpf():
    db = build_session()
    user = create_user(db, cpf=None)

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).start_checkout(user)

    assert exc.value.status_code == 422


def test_start_checkout_creates_customer_and_subscription(monkeypatch):
    db = build_session()
    user = create_user(db)
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    result = PaymentService(db).start_checkout(user)

    assert result["checkout_url"] == fake_client.invoice_url
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).one()
    assert subscription.provider_customer_id == fake_client.customer_id
    assert subscription.provider_subscription_id == fake_client.subscription_id


def test_start_checkout_reuses_existing_asaas_subscription(monkeypatch):
    db = build_session()
    user = create_user(db)
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    PaymentService(db).start_checkout(user)
    post_calls_after_first = len([c for c in fake_client.calls if c[0].endswith("/subscriptions")])
    PaymentService(db).start_checkout(user)
    post_calls_after_second = len([c for c in fake_client.calls if c[0].endswith("/subscriptions")])

    assert post_calls_after_first == 1
    assert post_calls_after_second == 1, "should not create a second Asaas subscription"


def test_webhook_payment_confirmed_activates_subscription():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(
        user_id=user.id,
        status=SubscriptionStatusEnum.PENDING.value,
        provider_subscription_id="sub_123",
    )
    db.add(subscription)
    db.commit()

    PaymentService(db).handle_webhook_event(
        {
            "event": "PAYMENT_CONFIRMED",
            "payment": {"subscription": "sub_123", "dueDate": "2026-09-25"},
        }
    )

    db.refresh(subscription)
    assert subscription.status == SubscriptionStatusEnum.ACTIVE.value


def test_webhook_payment_overdue_marks_past_due():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value, provider_subscription_id="sub_123")
    db.add(subscription)
    db.commit()

    PaymentService(db).handle_webhook_event({"event": "PAYMENT_OVERDUE", "payment": {"subscription": "sub_123"}})

    db.refresh(subscription)
    assert subscription.status == SubscriptionStatusEnum.PAST_DUE.value


def test_webhook_subscription_deleted_cancels():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value, provider_subscription_id="sub_123")
    db.add(subscription)
    db.commit()

    PaymentService(db).handle_webhook_event({"event": "SUBSCRIPTION_DELETED", "payment": {"subscription": "sub_123"}})

    db.refresh(subscription)
    assert subscription.status == SubscriptionStatusEnum.CANCELED.value


def test_webhook_for_unknown_subscription_is_ignored():
    db = build_session()

    # Should not raise even though no Subscription row matches.
    PaymentService(db).handle_webhook_event({"event": "PAYMENT_CONFIRMED", "payment": {"subscription": "unknown"}})

    assert db.query(Subscription).count() == 0


def test_is_active_reflects_subscription_status():
    db = build_session()
    user = create_user(db)
    assert PaymentService(db).is_active(user) is False

    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value))
    db.commit()

    assert PaymentService(db).is_active(user) is True
