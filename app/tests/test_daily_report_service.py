from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
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


def test_daily_report_button_flow_complete():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
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
        suspected_cause="Dormi mal",
    )

    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.awaiting_response is False
    assert report.awaiting_cause is False
    assert report.had_symptoms is True
    assert report.symptom_description == "Dor de cabeça corrigida"
    assert report.suspected_cause == "Dormi mal"


def test_update_patient_response_clears_text_when_marked_without_symptoms():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    DailyReportService.update_patient_response(
        db,
        report,
        had_symptoms=False,
        symptom_description="Texto que deve ser removido",
        suspected_cause="Causa que deve ser removida",
    )

    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.had_symptoms is False
    assert report.symptom_description is None
    assert report.suspected_cause is None


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

    DailyReportService.delete_patient_response(db, report)

    assert report.completed is False
    assert report.status == DailyReportStatusEnum.PENDING
    assert report.awaiting_response is True
    assert report.awaiting_cause is False
    assert report.had_symptoms is None
    assert report.symptom_description is None
    assert report.suspected_cause is None
