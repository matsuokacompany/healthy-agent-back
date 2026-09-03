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
    DailyReportStatusEnum,
    MonitoringPlan,
    Notification,
    NotificationKindEnum,
    User,
)


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@pytest.fixture(autouse=True)
def patch_session_local(monkeypatch):
    db = build_session()
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)
    return db


def _create_report(db, *, status, completed, report_date=None):
    user = User(name="Paciente", email=f"p-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.flush()
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.flush()
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=report_date or date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=status,
        completed=completed,
        awaiting_response=not completed,
        awaiting_cause=False,
        prompt_sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    return user, report


def test_pending_report_today_gets_a_reminder(patch_session_local):
    db = patch_session_local
    user, _ = _create_report(db, status=DailyReportStatusEnum.PENDING, completed=False)
    user_id = user.id

    asyncio.run(scheduler_module.send_checkin_reminders())

    notifications = db.query(Notification).filter(Notification.user_id == user_id).all()
    assert len(notifications) == 1
    assert notifications[0].kind == NotificationKindEnum.CHECKIN_PENDING.value


def test_completed_report_does_not_get_a_reminder(patch_session_local):
    db = patch_session_local
    _create_report(db, status=DailyReportStatusEnum.COMPLETED, completed=True)

    asyncio.run(scheduler_module.send_checkin_reminders())

    assert db.query(Notification).count() == 0


def test_pending_report_from_a_previous_day_does_not_get_a_reminder(patch_session_local):
    db = patch_session_local
    _create_report(
        db,
        status=DailyReportStatusEnum.PENDING,
        completed=False,
        report_date=date.today() - timedelta(days=1),
    )

    asyncio.run(scheduler_module.send_checkin_reminders())

    assert db.query(Notification).count() == 0


def test_reminder_is_not_duplicated_on_a_second_run_same_day(patch_session_local):
    db = patch_session_local
    user, _ = _create_report(db, status=DailyReportStatusEnum.PENDING, completed=False)
    user_id = user.id

    asyncio.run(scheduler_module.send_checkin_reminders())
    asyncio.run(scheduler_module.send_checkin_reminders())

    assert db.query(Notification).filter(Notification.user_id == user_id).count() == 1


def test_awaiting_symptom_description_report_gets_a_reminder(patch_session_local):
    db = patch_session_local
    user, _ = _create_report(db, status=DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION, completed=False)
    user_id = user.id

    asyncio.run(scheduler_module.send_checkin_reminders())

    assert db.query(Notification).filter(Notification.user_id == user_id).count() == 1
