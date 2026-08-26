import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.bot.scheduler as scheduler_module
from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
)


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class FakeChannel:
    def __init__(self):
        self.sent_to = []

    async def send_template(self, *, user, check_type, report_date):
        self.sent_to.append(user.id)
        return f"wa-{user.id}"


class FakeBotManager:
    def __init__(self, channel):
        self.channel = channel

    def get_channel_for_user(self, user):
        return self.channel if user.phone else None


@pytest.fixture(autouse=True)
def patch_session_local(monkeypatch):
    db = build_session()
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)
    return db


def _create_user_with_plan(db, *, name, origin, subscription_kwargs=None):
    user = User(name=name, email=f"{name.lower()}@example.com", phone="5511999990000")
    db.add(user)
    db.flush()
    plan = MonitoringPlan(
        patient_id=user.id,
        title="Plano",
        active=True,
        start_date=date.today() - timedelta(days=2),
        origin=origin,
    )
    db.add(plan)
    if subscription_kwargs is not None:
        db.add(Subscription(user_id=user.id, **subscription_kwargs))
    db.commit()
    return user


def test_self_service_plan_without_subscription_is_skipped(patch_session_local):
    db = patch_session_local
    _create_user_with_plan(
        db,
        name="SemAssinatura",
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
        subscription_kwargs=None,
    )
    channel = FakeChannel()
    bot_manager = FakeBotManager(channel)

    asyncio.run(scheduler_module.send_prompt(bot_manager, CheckTypeEnum.MORNING))

    assert channel.sent_to == []
    assert db.query(DailyReport).count() == 0


def test_self_service_plan_with_expired_trial_is_skipped(patch_session_local):
    db = patch_session_local
    _create_user_with_plan(
        db,
        name="TesteExpirado",
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
        subscription_kwargs={
            "status": SubscriptionStatusEnum.TRIALING.value,
            "trial_ends_at": datetime.now(timezone.utc) - timedelta(days=1),
        },
    )
    channel = FakeChannel()
    bot_manager = FakeBotManager(channel)

    asyncio.run(scheduler_module.send_prompt(bot_manager, CheckTypeEnum.MORNING))

    assert channel.sent_to == []
    assert db.query(DailyReport).count() == 0


def test_self_service_plan_within_trial_is_sent(patch_session_local):
    db = patch_session_local
    user = _create_user_with_plan(
        db,
        name="EmTeste",
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
        subscription_kwargs={
            "status": SubscriptionStatusEnum.TRIALING.value,
            "trial_ends_at": datetime.now(timezone.utc) + timedelta(days=10),
        },
    )
    channel = FakeChannel()
    bot_manager = FakeBotManager(channel)

    asyncio.run(scheduler_module.send_prompt(bot_manager, CheckTypeEnum.MORNING))

    assert channel.sent_to == [user.id]
    assert db.query(DailyReport).count() == 1


def test_self_service_plan_with_active_subscription_is_sent(patch_session_local):
    db = patch_session_local
    user = _create_user_with_plan(
        db,
        name="Assinante",
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
        subscription_kwargs={"status": SubscriptionStatusEnum.ACTIVE.value},
    )
    channel = FakeChannel()
    bot_manager = FakeBotManager(channel)

    asyncio.run(scheduler_module.send_prompt(bot_manager, CheckTypeEnum.MORNING))

    assert channel.sent_to == [user.id]


def test_professional_plan_is_unaffected_by_subscription_state(patch_session_local):
    db = patch_session_local
    user = _create_user_with_plan(
        db,
        name="PacienteProfissional",
        origin=MonitoringPlanOriginEnum.PROFESSIONAL.value,
        subscription_kwargs=None,
    )
    channel = FakeChannel()
    bot_manager = FakeBotManager(channel)

    asyncio.run(scheduler_module.send_prompt(bot_manager, CheckTypeEnum.MORNING))

    assert channel.sent_to == [user.id]
