from datetime import date, datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    MonitoringProfessional,
    Notification,
    NotificationKindEnum,
    ProfessionalProfile,
    SymptomTerm,
    User,
)
from app.services.daily_report_service import DailyReportService


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def create_user_and_plan(db):
    user = User(name="Teste", email=f"u-{datetime.now().timestamp()}@example.com", phone=str(datetime.now().timestamp()).replace('.', ''))
    db.add(user)
    db.commit()
    db.refresh(user)
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return user, plan


def create_user_and_self_service_plan(db):
    user = User(name="Teste", email=f"u-{datetime.now().timestamp()}@example.com", phone=str(datetime.now().timestamp()).replace('.', ''))
    db.add(user)
    db.commit()
    db.refresh(user)
    plan = MonitoringPlan(
        patient_id=user.id,
        title="Plano",
        active=True,
        start_date=date.today(),
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return user, plan


def test_daily_report_button_flow_complete():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    report.suspected_cause = "Causa antiga"
    db.commit()
    db.refresh(plan)

    assert DailyReportService.process_response(db, user, "Tive sintomas") == "ASK_SYMPTOM_DESCRIPTION"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION
    assert report.had_symptoms is True
    assert report.symptom_description is None

    assert DailyReportService.process_response(db, user, "Dor de cabeça e tontura") == "COMPLETED"

    db.refresh(report)
    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.symptom_description == "Dor de cabeça e tontura"
    assert report.suspected_cause is None


def test_self_service_plan_asks_combined_lifestyle_question_after_positive_symptoms():
    db = build_session()
    user, plan = create_user_and_self_service_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)

    assert DailyReportService.process_response(db, user, "Tive sintomas") == "ASK_SYMPTOM_DESCRIPTION"
    assert DailyReportService.process_response(db, user, "Dor de cabeça") == "ASK_MEDICATION_ADHERENCE"

    db.refresh(report)
    assert report.status == DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE
    assert report.completed is False
    assert report.had_symptoms is True
    assert report.symptom_description == "Dor de cabeça"

    # No OPENAI_API_KEY configured in this test environment, so
    # LifestyleAdherenceService no-ops -- the raw reply still gets saved,
    # only the two derived booleans stay unset (covered with the AI mocked
    # in test_lifestyle_adherence_service.py).
    assert DailyReportService.process_response(db, user, "Segui a dieta certinho e tomei os remédios") == "COMPLETED"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.completed is True
    assert report.lifestyle_notes == "Segui a dieta certinho e tomei os remédios"
    assert report.diet_adherence is None
    assert report.medication_adherence is None


def test_self_service_plan_asks_combined_lifestyle_question_after_negative_symptoms():
    db = build_session()
    user, plan = create_user_and_self_service_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)

    assert DailyReportService.process_response(db, user, "Não tive sintomas") == "ASK_MEDICATION_ADHERENCE"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE
    assert report.had_symptoms is False
    assert report.completed is False

    assert DailyReportService.process_response(db, user, "Não segui a dieta, comi doce; remédio tomei certinho") == "COMPLETED"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.completed is True
    assert report.lifestyle_notes == "Não segui a dieta, comi doce; remédio tomei certinho"


def test_professional_plan_completes_without_asking_lifestyle_question():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)

    assert DailyReportService.process_response(db, user, "Não tive sintomas") == "NEGATIVE"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.completed is True
    assert report.diet_adherence is None
    assert report.medication_adherence is None
    assert report.lifestyle_notes is None


def link_professional(db, patient_plan):
    professional_user = User(
        name="Dra. Teste",
        email=f"pro-{datetime.now().timestamp()}@example.com",
    )
    db.add(professional_user)
    db.commit()
    db.refresh(professional_user)
    profile = ProfessionalProfile(user_id=professional_user.id, active=True)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=patient_plan.id,
            professional_profile_id=profile.id,
            role="responsável",
            active=True,
        )
    )
    db.commit()
    return professional_user


def test_daily_report_symptom_notifies_assigned_professional():
    db = build_session()
    user, plan = create_user_and_plan(db)
    professional_user = link_professional(db, plan)
    DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)

    assert DailyReportService.process_response(db, user, "Tive sintomas") == "ASK_SYMPTOM_DESCRIPTION"
    # The bot's yes/no step doesn't have the symptom description yet, so it
    # shouldn't notify anyone until the report actually completes below.
    assert db.query(Notification).count() == 0

    assert DailyReportService.process_response(db, user, "Dor de cabeça e tontura") == "COMPLETED"

    notifications = db.query(Notification).filter(Notification.user_id == professional_user.id).all()
    assert len(notifications) == 1
    assert notifications[0].kind == NotificationKindEnum.SYMPTOM_REPORTED.value
    assert user.name in notifications[0].message


def test_daily_report_no_symptoms_does_not_notify():
    db = build_session()
    user, plan = create_user_and_plan(db)
    link_professional(db, plan)
    DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)

    assert DailyReportService.process_response(db, user, "Não tive sintomas") == "NEGATIVE"

    assert db.query(Notification).count() == 0


def test_daily_report_expired():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.NIGHT,
        status=DailyReportStatusEnum.PENDING,
        completed=False,
        awaiting_response=True,
        awaiting_cause=False,
        prompt_sent_at=datetime.now(timezone.utc) - timedelta(hours=25),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(report)
    db.commit()

    assert DailyReportService.process_response(db, user, "Senti náusea") == "EXPIRED"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.EXPIRED


def test_daily_report_negative_completes_open_report():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    assert DailyReportService.process_response(db, user, "Não tive sintomas") == "NEGATIVE"

    db.refresh(report)
    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.had_symptoms is False
    assert report.awaiting_response is False
    assert report.awaiting_cause is False


def test_daily_report_free_text_symptom_completes_without_cause():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    assert DailyReportService.process_response(db, user, "Tive dor de cabeça") == "COMPLETED"

    db.refresh(report)
    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.awaiting_response is False
    assert report.awaiting_cause is False
    assert report.had_symptoms is True
    assert report.symptom_description == "Tive dor de cabeça"
    assert report.suspected_cause is None


def test_daily_report_symptom_details_complete_without_cause():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    assert DailyReportService.process_response(db, user, "Tive sintomas") == "ASK_SYMPTOM_DESCRIPTION"
    assert DailyReportService.process_response(db, user, "Dor de cabeça e tontura") == "COMPLETED"

    db.refresh(report)
    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.symptom_description == "Dor de cabeça e tontura"
    assert report.suspected_cause is None


def test_create_pending_report_reuses_same_plan_day_check():
    db = build_session()
    user, plan = create_user_and_plan(db)
    first = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()
    second = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    assert first.id == second.id
    assert db.query(DailyReport).count() == 1


def test_create_pending_report_accepts_explicit_report_date():
    db = build_session()
    user, plan = create_user_and_plan(db)
    yesterday = date.today() - timedelta(days=1)

    report = DailyReportService.create_pending_report(
        db,
        user=user,
        monitoring_plan=plan,
        check_type=CheckTypeEnum.MORNING,
        report_date=yesterday,
    )
    db.commit()

    assert report.report_date == yesterday


def test_create_pending_report_does_not_reset_pending_report_in_progress():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    report.had_symptoms = True
    report.symptom_description = "Dor de cabeça"
    report.status = DailyReportStatusEnum.AWAITING_CAUSE
    report.awaiting_response = False
    report.awaiting_cause = True
    original_prompt_sent_at = report.prompt_sent_at
    db.commit()

    reused = DailyReportService.create_pending_report(
        db,
        user=user,
        monitoring_plan=plan,
        check_type=CheckTypeEnum.MORNING,
        now=original_prompt_sent_at + timedelta(hours=2),
    )
    db.commit()
    db.refresh(report)

    assert reused.id == report.id
    assert report.had_symptoms is True
    assert report.symptom_description == "Dor de cabeça"
    assert report.status == DailyReportStatusEnum.AWAITING_CAUSE
    assert report.awaiting_response is False
    assert report.awaiting_cause is True
    assert as_utc(report.prompt_sent_at) == as_utc(original_prompt_sent_at)


def test_create_pending_report_reopens_expired_report():
    db = build_session()
    user, plan = create_user_and_plan(db)
    expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.EXPIRED,
        completed=False,
        awaiting_response=False,
        awaiting_cause=False,
        had_symptoms=True,
        symptom_description="Dor antiga",
        suspected_cause="Causa antiga",
        prompt_sent_at=expired_at - timedelta(hours=24),
        expires_at=expired_at,
    )
    db.add(report)
    db.commit()

    now = datetime.now(timezone.utc)
    reopened = DailyReportService.create_pending_report(
        db,
        user=user,
        monitoring_plan=plan,
        check_type=CheckTypeEnum.MORNING,
        now=now,
    )
    db.commit()
    db.refresh(report)

    assert reopened.id == report.id
    assert report.status == DailyReportStatusEnum.PENDING
    assert report.completed is False
    assert report.awaiting_response is True
    assert report.awaiting_cause is False
    assert report.had_symptoms is None
    assert report.symptom_description is None
    assert report.suspected_cause is None
    assert as_utc(report.prompt_sent_at) == now
    assert as_utc(report.expires_at) == now + timedelta(hours=DailyReportService.RESPONSE_WINDOW_HOURS)


def test_update_patient_response_marks_report_completed():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    DailyReportService.update_patient_response(
        db,
        report,
        had_symptoms=True,
        symptom_description="Dor de cabeça corrigida",
    )

    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.awaiting_response is False
    assert report.awaiting_cause is False
    assert report.had_symptoms is True
    assert report.symptom_description == "Dor de cabeça corrigida"
    assert report.suspected_cause is None


def test_update_patient_response_clears_text_when_marked_without_symptoms():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    report.suspected_cause = "Causa que deve ser removida"
    db.commit()

    DailyReportService.update_patient_response(
        db,
        report,
        had_symptoms=False,
        symptom_description="Texto que deve ser removido",
    )

    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.had_symptoms is False
    assert report.symptom_description is None
    assert report.suspected_cause is None


@pytest.mark.parametrize("description", [None, "", "   "])
def test_update_patient_response_requires_description_when_symptoms_are_reported(description):
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(
        db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING
    )
    db.commit()

    with pytest.raises(ValueError, match="symptom description is required"):
        DailyReportService.update_patient_response(
            db,
            report,
            had_symptoms=True,
            symptom_description=description,
        )

    assert report.completed is False
    assert report.status == DailyReportStatusEnum.PENDING


def test_update_patient_response_clears_stale_symptom_terms_when_marked_without_symptoms():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    term = SymptomTerm(label="Cefaleia")
    db.add(term)
    db.commit()
    db.refresh(term)
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=user.id))
    db.commit()

    DailyReportService.update_patient_response(
        db,
        report,
        had_symptoms=False,
        symptom_description=None,
    )

    remaining = (
        db.query(DailyReportSymptomTerm)
        .filter(DailyReportSymptomTerm.daily_report_id == report.id)
        .all()
    )
    assert remaining == []


def test_delete_patient_response_reopens_report_for_answering():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        had_symptoms=True,
        symptom_description="Dor antiga",
        suspected_cause="Causa antiga",
        prompt_sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(report)
    db.commit()

    term = SymptomTerm(label="Cefaleia")
    db.add(term)
    db.commit()
    db.refresh(term)
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=user.id))
    db.commit()

    DailyReportService.delete_patient_response(db, report)

    assert report.completed is False
    assert report.status == DailyReportStatusEnum.PENDING
    assert report.awaiting_response is True
    assert report.awaiting_cause is False
    assert report.had_symptoms is None
    assert report.symptom_description is None
    assert report.suspected_cause is None
    remaining = (
        db.query(DailyReportSymptomTerm)
        .filter(DailyReportSymptomTerm.daily_report_id == report.id)
        .all()
    )
    assert remaining == []
