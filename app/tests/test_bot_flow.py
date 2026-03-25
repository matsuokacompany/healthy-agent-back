from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, User
from app.services.bot_service import BotService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_bot_service_response_flow(monkeypatch):
    db = build_session()
    user = User(name="Teste", email="bot@example.com", telegram_id="555")
    db.add(user)
    db.commit()
    db.refresh(user)

    report = DailyReport(user_id=user.id, check_type=CheckTypeEnum.MORNING)
    db.add(report)
    db.flush()
    user.current_report_id = report.id
    db.commit()

    monkeypatch.setattr("app.services.bot_service.SessionLocal", lambda: db)

    service = BotService()

    first = service.process_incoming(
        channel="telegram",
        external_user_id="555",
        message_text="Tive tontura",
    )
    assert first.ask_followup is True

    second = service.process_incoming(
        channel="telegram",
        external_user_id="555",
        message_text="Comi algo diferente",
    )
    assert "registradas" in second.text
