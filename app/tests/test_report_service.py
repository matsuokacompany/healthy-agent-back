from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
from app.services.report_service import ReportService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def create_user_and_plan(db):
    user = User(name="Paciente", email="paciente@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)

    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return user, plan


def create_completed_report(db, *, user, plan, symptom, created_at):
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=created_at.date(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        symptom_description=symptom,
        suspected_cause="teste",
        had_symptoms=True,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        prompt_sent_at=created_at,
        expires_at=created_at + timedelta(hours=24),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(report)
    db.commit()
    return report


def test_report_service_supports_diario_period():
    db = build_session()
    user, plan = create_user_and_plan(db)
    now = datetime.now(timezone.utc)

    create_completed_report(db, user=user, plan=plan, symptom="Dor atual", created_at=now - timedelta(hours=12))
    create_completed_report(db, user=user, plan=plan, symptom="Dor anterior", created_at=now - timedelta(hours=36))
    create_completed_report(db, user=user, plan=plan, symptom="Dor antiga", created_at=now - timedelta(days=3))

    relatorio = ReportService(db).gerar_relatorio(user.id, "diario")

    assert "Dor atual".lower() in relatorio
    assert "Dor anterior".lower() in relatorio
    assert "Dor antiga".lower() not in relatorio
    assert "Período analisado" in relatorio
