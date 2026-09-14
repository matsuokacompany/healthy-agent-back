from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
from app.services.patient_dashboard_service import PatientDashboardService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def make_report(db, *, red_flag_category=None):
    user = User(name="Paciente", email=f"p-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)

    now = datetime.now(timezone.utc)
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
        symptom_description="Aperto no peito",
        red_flag_category=red_flag_category,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_build_report_item_surfaces_the_matched_red_flag_category():
    db = build_session()
    report = make_report(db, red_flag_category="cardiorrespiratorio")

    item = PatientDashboardService._build_report_item(report)

    assert item.red_flag_category == "cardiorrespiratorio"


def test_build_report_item_is_none_when_no_category_matched():
    db = build_session()
    report = make_report(db, red_flag_category=None)

    item = PatientDashboardService._build_report_item(report)

    assert item.red_flag_category is None
