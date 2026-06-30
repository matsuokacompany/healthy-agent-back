from datetime import date, datetime, timedelta, timezone

import pytest

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
    first = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Tive sintomas")
    assert first.ask_followup is True
    assert "Quais sintomas" in first.text

    second = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Tive tontura")
    assert second.ask_followup is True

    third = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Comi algo diferente")
    assert "concluído" in third.text


def test_bot_service_negative_flow(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="777")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Não tive sintomas")

    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False


@pytest.mark.asyncio
async def test_whatsapp_template_payload_matches_meta_header_and_body_variables():
    from app.bot.channels.whatsapp_channel import WhatsAppBotChannel

    captured_payload = {}

    async def fake_post(payload):
        captured_payload.update(payload)

    channel = WhatsAppBotChannel()
    channel._post = fake_post
    user = User(name="Igor", email="igor@example.com", phone="5543999999999")

    await channel.send_template(
        user=user,
        check_type=CheckTypeEnum.MORNING,
        report_date=date(2026, 6, 18),
    )

    components = captured_payload["template"]["components"]
    assert components == [
        {
            "type": "header",
            "parameters": [{"type": "text", "text": "Igor"}],
        },
        {
            "type": "body",
            "parameters": [{"type": "text", "text": "quinta-feira - 18/06/2026"}],
        },
    ]


def test_bot_service_matches_normalized_phone(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="5543935050108")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id="+55 (43) 93505-0108",
        message_text="Não tive sintomas",
    )

    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False


def test_bot_service_matches_stored_phone_after_normalizing_database_value(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="+55 (43) 99126-6196")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id="5543991266196",
        message_text="Não tive sintomas",
    )

    assert user.phone == "+55 (43) 99126-6196"
    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False


def test_bot_service_matches_brazilian_whatsapp_id_without_extra_ninth_digit(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="5543991266196")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id="554391266196",
        message_text="Não tive sintomas",
    )

    assert user.phone == "5543991266196"
    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False
