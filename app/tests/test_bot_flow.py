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

    db.refresh(user)
    assert user.phone == "5543991266196"
    assert user.whatsapp_wa_id == "554391266196"
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


def test_wa_id_link_conflict_uses_savepoint_without_global_rollback():
    class FakeQuery:
        def __init__(self, result=None, results=None):
            self.result = result
            self.results = results or []

        def filter(self, *args, **kwargs):
            return self

        def limit(self, value):
            return self

        def first(self):
            return self.result

        def all(self):
            return self.results

    class FakeNestedTransaction:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeDb:
        def __init__(self, candidate):
            self.candidate = candidate
            self.rolled_back = False
            self.expired = False
            self.query_count = 0

        def query(self, model):
            self.query_count += 1
            if self.query_count == 1:
                return FakeQuery(result=None)
            return FakeQuery(results=[self.candidate])

        def begin_nested(self):
            return FakeNestedTransaction()

        def flush(self):
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("update", {}, Exception("unique violation"))

        def rollback(self):
            self.rolled_back = True

        def expire(self, instance, attrs):
            self.expired = True

    candidate = User(id=123, name="Paciente", email="paciente@example.com", phone="5543991266196")
    db = FakeDb(candidate)

    user = BotService._find_user_by_whatsapp_identity(
        db,
        external_user_id="554391266196",
        normalized_wa_id="554391266196",
    )

    assert user is None
    assert db.expired is True
    assert db.rolled_back is False


def test_bot_service_marks_message_failed_when_clinical_processing_errors(monkeypatch):
    db = build_session()
    user, _ = create_pending_report(db, phone="5543991266196")
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    class FailingDailyReportService:
        def process_response(self, db, user, message_text):
            from sqlalchemy.exc import SQLAlchemyError
            raise SQLAlchemyError("boom")

    service = BotService(daily_report_service=FailingDailyReportService())
    response = service.process_incoming(
        channel="whatsapp",
        external_user_id=user.phone,
        message_text="Não tive sintomas",
        message_id="wamid.failed-processing",
    )

    message = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == "wamid.failed-processing").first()
    assert "Não consegui processar" in response.text
    assert message is not None
    assert message.status == "FAILED"
    assert message.response_text == response.text


def test_bot_service_recovers_stale_processing_messages(monkeypatch):
    db = build_session()
    stale_created_at = datetime.now(timezone.utc) - timedelta(minutes=BotService.PROCESSING_TIMEOUT_MINUTES + 1)
    message = WhatsAppMessage(
        message_id="wamid.stale-processing",
        channel="whatsapp",
        external_user_id="5543991266196",
        normalized_user_id="5543991266196",
        status="PROCESSING",
        created_at=stale_created_at,
    )
    db.add(message)
    db.commit()
    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    reserved = BotService._reserve_message(
        message_id="wamid.stale-processing",
        channel="whatsapp",
        external_user_id="5543991266196",
        normalized_user_id="5543991266196",
    )

    db.refresh(message)
    assert reserved is False
    assert message.status == "FAILED"
    assert message.response_text == "Processing timed out before completion"
    assert message.processed_at is not None
