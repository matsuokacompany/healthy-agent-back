from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
from app.services.daily_report_service import DailyReportService


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

    assert DailyReportService.process_response(db, user, "Tive sintomas") == "ASK_SYMPTOM_DESCRIPTION"
    db.refresh(report)
    assert report.status == DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION
    assert report.had_symptoms is True
    assert report.symptom_description is None

    assert DailyReportService.process_response(db, user, "Dor de cabeça") == "ASK_CAUSE"
    assert DailyReportService.process_response(db, user, "Dormi tarde") == "COMPLETED"

    db.refresh(report)
    assert report.completed is True
    assert report.status == DailyReportStatusEnum.COMPLETED
    assert report.symptom_description == "Dor de cabeça"
    assert report.suspected_cause == "Dormi tarde"


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


def test_daily_report_free_text_symptom_asks_cause():
    db = build_session()
    user, plan = create_user_and_plan(db)
    report = DailyReportService.create_pending_report(db, user=user, monitoring_plan=plan, check_type=CheckTypeEnum.MORNING)
    db.commit()

    assert DailyReportService.process_response(db, user, "Tive dor de cabeça") == "ASK_CAUSE"

    db.refresh(report)
    assert report.completed is False
    assert report.status == DailyReportStatusEnum.AWAITING_CAUSE
    assert report.awaiting_response is False
    assert report.awaiting_cause is True
    assert report.had_symptoms is True
    assert report.symptom_description == "Tive dor de cabeça"


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
