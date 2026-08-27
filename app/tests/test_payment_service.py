from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import Subscription, SubscriptionStatusEnum, User
from app.services.payment_service import PaymentService, subscription_grants_access


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

    def __init__(
        self,
        *,
        customer_id="cus_123",
        subscription_id="sub_123",
        invoice_url="https://asaas.test/i/abc",
        payment_id="pay_123",
        payment_status="CONFIRMED",
    ):
        self.customer_id = customer_id
        self.subscription_id = subscription_id
        self.invoice_url = invoice_url
        self.payment_id = payment_id
        self.payment_status = payment_status
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
        if url.endswith("/refund"):
            return FakeResponse(200, {})
        raise AssertionError(f"Unexpected POST {url}")

    def get(self, url, headers=None, params=None):
        self.calls.append((url, params))
        if url.endswith("/payments"):
            return FakeResponse(200, {"data": [{"id": self.payment_id, "invoiceUrl": self.invoice_url, "status": self.payment_status}]})
        raise AssertionError(f"Unexpected GET {url}")

    def delete(self, url, headers=None):
        self.calls.append((url, None))
        if "/subscriptions/" in url:
            return FakeResponse(200, {"deleted": True})
        raise AssertionError(f"Unexpected DELETE {url}")


@pytest.fixture(autouse=True)
def asaas_settings(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASAAS_ENV", "sandbox")
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", 2990)
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", "shared-secret")


def test_start_checkout_requires_valid_plan(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", None)
    db = build_session()
    user = create_user(db)

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).start_checkout(user, "monthly")

    assert exc.value.status_code == 400


def test_start_checkout_requires_cpf():
    db = build_session()
    user = create_user(db, cpf=None)

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).start_checkout(user, "monthly")

    assert exc.value.status_code == 422


def test_start_checkout_creates_customer_and_subscription(monkeypatch):
    db = build_session()
    user = create_user(db)
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    result = PaymentService(db).start_checkout(user, "monthly")

    assert result["checkout_url"] == fake_client.invoice_url
    assert result["plan_id"] == "monthly"
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).one()
    assert subscription.provider_customer_id == fake_client.customer_id
    assert subscription.provider_subscription_id == fake_client.subscription_id
    assert subscription.plan_id == "monthly"


def test_start_checkout_reuses_existing_asaas_subscription(monkeypatch):
    db = build_session()
    user = create_user(db)
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    PaymentService(db).start_checkout(user, "monthly")
    post_calls_after_first = len([c for c in fake_client.calls if c[0].endswith("/subscriptions")])
    PaymentService(db).start_checkout(user, "monthly")
    post_calls_after_second = len([c for c in fake_client.calls if c[0].endswith("/subscriptions")])

    assert post_calls_after_first == 1
    assert post_calls_after_second == 1, "should not create a second Asaas subscription"


def test_start_checkout_creates_new_asaas_subscription_when_plan_changes(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS", 9990)
    db = build_session()
    user = create_user(db)
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    PaymentService(db).start_checkout(user, "monthly")
    PaymentService(db).start_checkout(user, "semiannual")

    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).one()
    assert subscription.plan_id == "semiannual"
    subscription_calls = [c for c in fake_client.calls if c[0].endswith("/subscriptions")]
    assert len(subscription_calls) == 2
    assert subscription_calls[1][1]["cycle"] == "SEMIANNUALLY"


def test_start_checkout_blocks_plan_change_while_active(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS", 9990)
    db = build_session()
    user = create_user(db)
    db.add(
        Subscription(
            user_id=user.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            provider_subscription_id="sub_123",
            plan_id="monthly",
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).start_checkout(user, "semiannual")

    assert exc.value.status_code == 409


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


def test_has_access_reflects_subscription_status():
    db = build_session()
    user = create_user(db)
    assert PaymentService(db).has_access(user) is False

    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value))
    db.commit()

    assert PaymentService(db).has_access(user) is True


def test_subscription_grants_access_for_none():
    assert subscription_grants_access(None) is False


def test_subscription_grants_access_during_trial():
    subscription = Subscription(
        status=SubscriptionStatusEnum.TRIALING.value,
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert subscription_grants_access(subscription) is True


def test_subscription_denies_access_after_trial_expires():
    subscription = Subscription(
        status=SubscriptionStatusEnum.TRIALING.value,
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert subscription_grants_access(subscription) is False


def test_subscription_denies_access_when_past_due_or_canceled():
    assert subscription_grants_access(Subscription(status=SubscriptionStatusEnum.PAST_DUE.value)) is False
    assert subscription_grants_access(Subscription(status=SubscriptionStatusEnum.CANCELED.value)) is False


def test_start_trial_if_needed_starts_trial_once():
    db = build_session()
    user = create_user(db)

    subscription = PaymentService(db).start_trial_if_needed(user)

    assert subscription.status == SubscriptionStatusEnum.TRIALING.value
    assert subscription.trial_ends_at is not None
    trial_ends_at = subscription.trial_ends_at.replace(tzinfo=timezone.utc)
    expected = datetime.now(timezone.utc) + timedelta(days=settings.ASAAS_SELF_MONITORING_TRIAL_DAYS)
    assert abs((trial_ends_at - expected).total_seconds()) < 5


def test_start_trial_if_needed_is_a_noop_once_active():
    db = build_session()
    user = create_user(db)
    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value, trial_ends_at=None))
    db.commit()

    subscription = PaymentService(db).start_trial_if_needed(user)

    assert subscription.status == SubscriptionStatusEnum.ACTIVE.value
    assert subscription.trial_ends_at is None


def test_cancel_subscription_marks_cancel_at_period_end_and_calls_asaas(monkeypatch):
    db = build_session()
    user = create_user(db)
    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value, provider_subscription_id="sub_123"))
    db.commit()
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    subscription = PaymentService(db).cancel_subscription(user)

    assert subscription.cancel_at_period_end is True
    assert subscription.status == SubscriptionStatusEnum.ACTIVE.value
    delete_calls = [c for c in fake_client.calls if "/subscriptions/" in c[0]]
    assert len(delete_calls) == 1


def test_cancel_subscription_is_idempotent(monkeypatch):
    db = build_session()
    user = create_user(db)
    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.ACTIVE.value, provider_subscription_id="sub_123"))
    db.commit()
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    PaymentService(db).cancel_subscription(user)
    PaymentService(db).cancel_subscription(user)

    delete_calls = [c for c in fake_client.calls if "/subscriptions/" in c[0]]
    assert len(delete_calls) == 1, "should not call Asaas twice for an already-canceled subscription"


def test_cancel_subscription_rejects_when_not_active():
    db = build_session()
    user = create_user(db)

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).cancel_subscription(user)

    assert exc.value.status_code == 409


def test_subscription_grants_access_until_period_end_after_cancel():
    subscription = Subscription(
        status=SubscriptionStatusEnum.ACTIVE.value,
        cancel_at_period_end=True,
        current_period_end=datetime.now(timezone.utc) + timedelta(days=3),
    )
    assert subscription_grants_access(subscription) is True

    subscription.current_period_end = datetime.now(timezone.utc) - timedelta(days=1)
    assert subscription_grants_access(subscription) is False


def test_refund_subscription_within_window_refunds_and_cancels(monkeypatch):
    db = build_session()
    user = create_user(db)
    db.add(
        Subscription(
            user_id=user.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            provider_subscription_id="sub_123",
            first_paid_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
    )
    db.commit()
    fake_client = FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    subscription = PaymentService(db).refund_subscription(user)

    assert subscription.status == SubscriptionStatusEnum.CANCELED.value
    refund_calls = [c for c in fake_client.calls if c[0].endswith("/refund")]
    assert len(refund_calls) == 1


def test_refund_subscription_rejects_outside_window():
    db = build_session()
    user = create_user(db)
    db.add(
        Subscription(
            user_id=user.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            provider_subscription_id="sub_123",
            first_paid_at=datetime.now(timezone.utc) - timedelta(days=8),
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).refund_subscription(user)

    assert exc.value.status_code == 409
    assert exc.value.detail == "REFUND_WINDOW_EXPIRED"


def test_refund_subscription_rejects_without_any_payment():
    db = build_session()
    user = create_user(db)
    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.PENDING.value))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).refund_subscription(user)

    assert exc.value.status_code == 409
    assert exc.value.detail == "NO_PAYMENT_TO_REFUND"


def test_webhook_payment_confirmed_sets_first_paid_at_once():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(user_id=user.id, status=SubscriptionStatusEnum.PENDING.value, provider_subscription_id="sub_123")
    db.add(subscription)
    db.commit()

    PaymentService(db).handle_webhook_event({"event": "PAYMENT_CONFIRMED", "payment": {"subscription": "sub_123", "dueDate": "2026-09-25"}})
    db.refresh(subscription)
    first_paid_at = subscription.first_paid_at
    assert first_paid_at is not None

    PaymentService(db).handle_webhook_event({"event": "PAYMENT_CONFIRMED", "payment": {"subscription": "sub_123", "dueDate": "2026-10-25"}})
    db.refresh(subscription)
    assert subscription.first_paid_at == first_paid_at, "first_paid_at should not move on a later renewal payment"
