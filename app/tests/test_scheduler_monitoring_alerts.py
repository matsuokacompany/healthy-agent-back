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
    DailyReportSymptomTerm,
    MedicationAdherenceLevelEnum,
    MonitoringPlan,
    MonitoringProfessional,
    Notification,
    NotificationKindEnum,
    ProfessionalProfile,
    SymptomTerm,
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


def make_patient(db):
    user = User(name="Paciente", email=f"p-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.flush()
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today() - timedelta(days=30))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return user, plan


def assign_professional(db, plan):
    professional_user = User(name="Profissional", email=f"pro-{datetime.now().timestamp()}@example.com")
    db.add(professional_user)
    db.flush()
    profile = ProfessionalProfile(user_id=professional_user.id, active=True)
    db.add(profile)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, role="responsável", active=True))
    db.commit()
    return professional_user


def add_report(db, plan, user, *, report_date, completed, medication_adherence_level=None):
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED if completed else DailyReportStatusEnum.PENDING,
        completed=completed,
        awaiting_response=not completed,
        awaiting_cause=False,
        medication_adherence_level=medication_adherence_level,
        prompt_sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def add_symptom_report(db, plan, user, *, report_date, term_label):
    report = add_report(db, plan, user, report_date=report_date, completed=True)
    term = db.query(SymptomTerm).filter(SymptomTerm.label == term_label).first()
    if not term:
        term = SymptomTerm(label=term_label)
        db.add(term)
        db.flush()
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=user.id))
    db.commit()
    return report


# --- inactivity ---------------------------------------------------------

def test_three_consecutive_incomplete_reports_notifies_self_service_patient(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    patient_id = patient.id
    for offset in range(1, 4):
        add_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), completed=False)

    asyncio.run(scheduler_module.send_monitoring_alerts())

    notifications = db.query(Notification).filter(Notification.kind == NotificationKindEnum.PATIENT_INACTIVE.value).all()
    assert len(notifications) == 1
    assert notifications[0].user_id == patient_id


def test_two_consecutive_incomplete_reports_does_not_notify(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    for offset in range(1, 3):
        add_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), completed=False)

    asyncio.run(scheduler_module.send_monitoring_alerts())

    assert db.query(Notification).filter(Notification.kind == NotificationKindEnum.PATIENT_INACTIVE.value).count() == 0


def test_three_consecutive_incomplete_reports_notifies_assigned_professional(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    professional = assign_professional(db, plan)
    professional_id = professional.id
    patient_name = patient.name
    for offset in range(1, 4):
        add_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), completed=False)

    asyncio.run(scheduler_module.send_monitoring_alerts())

    notification = db.query(Notification).filter(Notification.kind == NotificationKindEnum.PATIENT_INACTIVE.value).one()
    assert notification.user_id == professional_id
    assert patient_name in notification.message


def test_eighth_consecutive_incomplete_report_does_not_notify_again(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    for offset in range(1, 9):
        add_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), completed=False)

    asyncio.run(scheduler_module.send_monitoring_alerts())

    # Streak is 8, past both alert thresholds (3, 7) -- the escalation
    # already fired back on day 7, so day 8 of the same silence stays quiet
    # instead of re-alerting on every subsequent day.
    assert db.query(Notification).filter(Notification.kind == NotificationKindEnum.PATIENT_INACTIVE.value).count() == 0


# --- medication adherence ------------------------------------------------

def test_two_consecutive_none_adherence_notifies(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    patient_id = patient.id
    for offset in range(1, 3):
        add_report(
            db, plan, patient,
            report_date=date.today() - timedelta(days=offset),
            completed=True,
            medication_adherence_level=MedicationAdherenceLevelEnum.NONE.value,
        )

    asyncio.run(scheduler_module.send_monitoring_alerts())

    notifications = db.query(Notification).filter(Notification.kind == NotificationKindEnum.MEDICATION_ADHERENCE_ALERT.value).all()
    assert len(notifications) == 1
    assert notifications[0].user_id == patient_id


def test_three_consecutive_none_adherence_does_not_refire(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    for offset in range(1, 4):
        add_report(
            db, plan, patient,
            report_date=date.today() - timedelta(days=offset),
            completed=True,
            medication_adherence_level=MedicationAdherenceLevelEnum.NONE.value,
        )

    asyncio.run(scheduler_module.send_monitoring_alerts())

    # The alert already fired on the day the streak reached two -- a third
    # consecutive NONE day is the same ongoing streak, not a new crossing.
    assert db.query(Notification).filter(Notification.kind == NotificationKindEnum.MEDICATION_ADHERENCE_ALERT.value).count() == 0


def test_partial_adherence_does_not_trigger_the_none_alert(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    for offset in range(1, 3):
        add_report(
            db, plan, patient,
            report_date=date.today() - timedelta(days=offset),
            completed=True,
            medication_adherence_level=MedicationAdherenceLevelEnum.PARTIAL.value,
        )

    asyncio.run(scheduler_module.send_monitoring_alerts())

    assert db.query(Notification).filter(Notification.kind == NotificationKindEnum.MEDICATION_ADHERENCE_ALERT.value).count() == 0


# --- symptom pattern ------------------------------------------------------

def test_same_symptom_three_times_in_seven_days_notifies(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    patient_id = patient.id
    for offset in (1, 3, 6):
        add_symptom_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), term_label="Dor de cabeça")

    asyncio.run(scheduler_module.send_monitoring_alerts())

    notifications = db.query(Notification).filter(Notification.kind == NotificationKindEnum.SYMPTOM_PATTERN_ALERT.value).all()
    assert len(notifications) == 1
    assert notifications[0].user_id == patient_id
    assert "Dor de cabeça" in notifications[0].message


def test_same_symptom_twice_in_seven_days_does_not_notify(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    for offset in (1, 3):
        add_symptom_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), term_label="Dor de cabeça")

    asyncio.run(scheduler_module.send_monitoring_alerts())

    assert db.query(Notification).filter(Notification.kind == NotificationKindEnum.SYMPTOM_PATTERN_ALERT.value).count() == 0


def test_symptom_pattern_alert_has_a_cooldown(patch_session_local):
    db = patch_session_local
    patient, plan = make_patient(db)
    for offset in (1, 3, 6):
        add_symptom_report(db, plan, patient, report_date=date.today() - timedelta(days=offset), term_label="Dor de cabeça")
    db.add(Notification(user_id=patient.id, kind=NotificationKindEnum.SYMPTOM_PATTERN_ALERT.value, message="já avisado"))
    db.commit()

    asyncio.run(scheduler_module.send_monitoring_alerts())

    assert db.query(Notification).filter(Notification.kind == NotificationKindEnum.SYMPTOM_PATTERN_ALERT.value).count() == 1
