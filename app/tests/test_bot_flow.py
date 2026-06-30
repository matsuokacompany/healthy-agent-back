from datetime import date, datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User, WhatsAppMessage
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
    first = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Tive sintomas", message_id="msg-flow-1")
    assert first.ask_followup is True
    assert "Quais sintomas" in first.text

    second = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Tive tontura", message_id="msg-flow-2")
    assert second.ask_followup is True

    third = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Comi algo diferente", message_id="msg-flow-3")
    assert "concluído" in third.text


def test_bot_service_negative_flow(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="777")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(channel="whatsapp", external_user_id=user.phone, message_text="Não tive sintomas", message_id="msg-negative-1")

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


@pytest.mark.asyncio
async def test_whatsapp_template_returns_meta_wa_id():
    from app.bot.channels.whatsapp_channel import WhatsAppBotChannel

    async def fake_post(payload):
        return {"contacts": [{"input": payload["to"], "wa_id": "554391266196"}]}

    channel = WhatsAppBotChannel()
    channel._post = fake_post
    user = User(name="Bete", email="bete@example.com", phone="5543991266196")

    wa_id = await channel.send_template(
        user=user,
        check_type=CheckTypeEnum.MORNING,
        report_date=date(2026, 6, 29),
    )

    assert wa_id == "554391266196"


def test_bot_service_matches_normalized_phone(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="5543935050108")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id="+55 (43) 93505-0108",
        message_text="Não tive sintomas",
        message_id="msg-normalized-1",
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
        message_id="msg-formatted-stored-1",
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
        message_id="msg-br-ninth-1",
    )

    db.refresh(user)
    assert user.phone == "5543991266196"
    assert user.whatsapp_wa_id == "554391266196"
    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False


def test_bot_service_uses_persisted_whatsapp_wa_id_as_primary_identity(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="5543991266196")
    user.whatsapp_wa_id = "554391266196"
    db.commit()
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id="554391266196",
        message_text="Não tive sintomas",
        message_id="msg-primary-wa-id-1",
    )

    assert "Obrigado por informar" in response.text
    assert response.ask_followup is False


def test_bot_service_links_wa_id_once_from_legacy_phone_match(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="5543991266196")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id="554391266196",
        message_text="Não tive sintomas",
        message_id="msg-legacy-wa-id-link-1",
    )

    db.refresh(user)
    assert "Obrigado por informar" in response.text
    assert user.whatsapp_wa_id == "554391266196"


def test_bot_service_ignores_duplicate_whatsapp_message_id(monkeypatch):
    db = build_session()
    user, report = create_pending_report(db, phone="5543991266196")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()
    first = service.process_incoming(
        channel="whatsapp",
        external_user_id=user.phone,
        message_text="Não tive sintomas",
        message_id="wamid.duplicate-test",
    )
    second = service.process_incoming(
        channel="whatsapp",
        external_user_id=user.phone,
        message_text="Não tive sintomas",
        message_id="wamid.duplicate-test",
    )

    db.refresh(report)
    assert "Obrigado por informar" in first.text
    assert second.duplicate is True
    assert second.text == ""
    assert report.completed is True
    assert db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == "wamid.duplicate-test").count() == 1


@pytest.mark.asyncio
async def test_whatsapp_channel_does_not_send_response_for_duplicate_message_id(monkeypatch):
    from app.bot.channels.whatsapp_channel import WhatsAppBotChannel

    db = build_session()
    user, _ = create_pending_report(db, phone="5543991266196")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)
    sent_payloads = []

    async def fake_post(payload):
        sent_payloads.append(payload)

    channel = WhatsAppBotChannel()
    channel._post = fake_post
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.channel-duplicate",
                                    "from": user.phone,
                                    "type": "text",
                                    "text": {"body": "Não tive sintomas"},
                                },
                                {
                                    "id": "wamid.channel-duplicate",
                                    "from": user.phone,
                                    "type": "text",
                                    "text": {"body": "Não tive sintomas"},
                                },
                            ]
                        }
                    }
                ]
            }
        ]
    }

    await channel.handle_incoming(payload)

    assert len(sent_payloads) == 1
    assert "Obrigado por informar" in sent_payloads[0]["text"]["body"]
