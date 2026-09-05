import asyncio
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.bot.scheduler as scheduler_module
from app.db.base_class import Base
from app.models.models import Notification, NotificationKindEnum, Supplement, User


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@pytest.fixture(autouse=True)
def patch_session_local(monkeypatch):
    db = build_session()
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)
    return db


def _create_patient_with_supplement(db, *, started_at, duration_days, ended_notification_sent_at=None):
    patient = User(name="Paciente", email="paciente@example.com")
    db.add(patient)
    db.flush()
    supplement = Supplement(
        patient_id=patient.id,
        name="Amoxicilina",
        started_at=started_at,
        duration_days=duration_days,
        ended_notification_sent_at=ended_notification_sent_at,
    )
    db.add(supplement)
    db.commit()
    return patient, supplement


def test_notifies_patient_once_course_has_ended(patch_session_local):
    db = patch_session_local
    patient, supplement = _create_patient_with_supplement(
        db, started_at=date.today() - timedelta(days=15), duration_days=10
    )
    patient_id, supplement_id = patient.id, supplement.id

    asyncio.run(scheduler_module.send_supplement_course_ended_notifications())

    # The scheduler job closes its session (the same one, shared via
    # patch_session_local) when done, detaching `patient`/`supplement`; query
    # fresh by the ids captured before the call instead of touching them.
    notifications = db.query(Notification).filter(Notification.user_id == patient_id).all()
    assert len(notifications) == 1
    assert notifications[0].kind == NotificationKindEnum.SUPPLEMENT_COURSE_ENDED.value
    reloaded = db.query(Supplement).filter(Supplement.id == supplement_id).one()
    assert reloaded.ended_notification_sent_at is not None


def test_does_not_notify_for_an_active_course(patch_session_local):
    db = patch_session_local
    patient, _ = _create_patient_with_supplement(db, started_at=date.today() - timedelta(days=2), duration_days=10)

    asyncio.run(scheduler_module.send_supplement_course_ended_notifications())

    assert db.query(Notification).count() == 0


def test_does_not_notify_for_an_indeterminate_course(patch_session_local):
    db = patch_session_local
    _create_patient_with_supplement(db, started_at=date.today() - timedelta(days=400), duration_days=None)

    asyncio.run(scheduler_module.send_supplement_course_ended_notifications())

    assert db.query(Notification).count() == 0


def test_does_not_re_notify_on_a_second_run(patch_session_local):
    db = patch_session_local
    patient, _ = _create_patient_with_supplement(db, started_at=date.today() - timedelta(days=15), duration_days=10)
    patient_id = patient.id

    asyncio.run(scheduler_module.send_supplement_course_ended_notifications())
    asyncio.run(scheduler_module.send_supplement_course_ended_notifications())

    assert db.query(Notification).filter(Notification.user_id == patient_id).count() == 1


def test_already_notified_course_is_skipped(patch_session_local):
    from datetime import datetime, timezone

    db = patch_session_local
    _create_patient_with_supplement(
        db,
        started_at=date.today() - timedelta(days=15),
        duration_days=10,
        ended_notification_sent_at=datetime.now(timezone.utc),
    )

    asyncio.run(scheduler_module.send_supplement_course_ended_notifications())

    assert db.query(Notification).count() == 0
