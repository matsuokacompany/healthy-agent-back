from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
from app.services.bot_service import BotService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def create_pending_report(db, phone="555"):
    user = User(name="Teste", email=f"bot-{phone}@example.com", phone=phone)
    db.add(user)
    db.commit()
    db.refresh(user)
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.PENDING,
        completed=False,
        awaiting_response=True,
        awaiting_cause=False,
        prompt_sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    return user, report


def test_bot_service_response_flow(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="555")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    first = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Tive tontura")
    assert first.ask_followup is True

    second = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Comi algo diferente")
    assert "concluído" in second.text


def test_bot_service_negative_flow(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="777")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Não tive sintomas")

    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False
