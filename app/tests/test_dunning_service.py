from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import Notification, Subscription, SubscriptionStatusEnum, User
from app.services.dunning_service import DunningService, notify_payment_overdue
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


def test_notify_payment_overdue_creates_notification():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(user_id=user.id, status=SubscriptionStatusEnum.PAST_DUE.value)
    db.add(subscription)
    db.commit()

    notify_payment_overdue(db, subscription, user)
    db.commit()

    notifications = db.query(Notification).filter(Notification.user_id == user.id).all()
    assert len(notifications) == 1
    assert notifications[0].kind == "PAYMENT_OVERDUE"


def test_trial_ending_reminder_sent_within_window_once():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(
        user_id=user.id,
        status=SubscriptionStatusEnum.TRIALING.value,
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db.add(subscription)
    db.commit()

    result = DunningService(db).run_daily_reminders()

    assert result["trial_ending"] == 1
    db.refresh(subscription)
    assert subscription.trial_ending_reminder_sent_at is not None
    assert db.query(Notification).filter(Notification.user_id == user.id, Notification.kind == "TRIAL_ENDING").count() == 1

    # Running again the same day must not double-send.
    result_again = DunningService(db).run_daily_reminders()
    assert result_again["trial_ending"] == 0
    assert db.query(Notification).filter(Notification.user_id == user.id, Notification.kind == "TRIAL_ENDING").count() == 1


def test_trial_ending_reminder_skipped_outside_window():
    db = build_session()
    user = create_user(db)
    db.add(
        Subscription(
            user_id=user.id,
            status=SubscriptionStatusEnum.TRIALING.value,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    db.commit()

    result = DunningService(db).run_daily_reminders()

    assert result["trial_ending"] == 0


def test_access_ending_reminder_sent_for_canceled_subscription_near_period_end():
    db = build_session()
    user = create_user(db)
    subscription = Subscription(
        user_id=user.id,
        status=SubscriptionStatusEnum.ACTIVE.value,
        cancel_at_period_end=True,
        current_period_end=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(subscription)
    db.commit()

    result = DunningService(db).run_daily_reminders()

    assert result["access_ending"] == 1
    db.refresh(subscription)
    assert subscription.access_ending_reminder_sent_at is not None
    assert db.query(Notification).filter(Notification.user_id == user.id, Notification.kind == "ACCESS_ENDING").count() == 1


def test_access_ending_reminder_skipped_when_not_canceled():
    db = build_session()
    user = create_user(db)
    db.add(
        Subscription(
            user_id=user.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            cancel_at_period_end=False,
            current_period_end=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    db.commit()

    result = DunningService(db).run_daily_reminders()

    assert result["access_ending"] == 0


def test_reactivating_a_canceled_subscription_resets_access_ending_reminder(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ASAAS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", 2990)
    db = build_session()
    user = create_user(db)
    subscription = Subscription(
        user_id=user.id,
        status=SubscriptionStatusEnum.ACTIVE.value,
        provider_customer_id="cus_123",
        provider_subscription_id="sub_123",
        plan_id="monthly",
        cancel_at_period_end=True,
        access_ending_reminder_sent_at=datetime.now(timezone.utc),
    )
    db.add(subscription)
    db.commit()

    class FakeAsaasClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None, params=None):
            return type("R", (), {"status_code": 200, "json": lambda self: {"data": []}})()

    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: FakeAsaasClient())

    PaymentService(db).start_checkout(user, "monthly")

    db.refresh(subscription)
    assert subscription.cancel_at_period_end is False
    assert subscription.access_ending_reminder_sent_at is None
