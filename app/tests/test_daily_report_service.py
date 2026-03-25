from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, User
from app.services.daily_report_service import DailyReportService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_daily_report_flow_complete():
    db = build_session()
    user = User(name="Teste", email="t@example.com", telegram_id="123")
    db.add(user)
    db.commit()
    db.refresh(user)

    report = DailyReport(user_id=user.id, check_type=CheckTypeEnum.MORNING)
    db.add(report)
    db.flush()
    user.current_report_id = report.id
    db.commit()

    status_first = DailyReportService.process_response(db, user, "Dor de cabeça")
    assert status_first == "ASK_CAUSE"

    status_second = DailyReportService.process_response(db, user, "Dormi tarde")
    assert status_second == "COMPLETED"

    db.refresh(report)
    assert report.completed is True
    assert report.symptom_description == "Dor de cabeça"
    assert report.suspected_cause == "Dormi tarde"


def test_daily_report_expired():
    db = build_session()
    user = User(name="Teste", email="expired@example.com", telegram_id="321")
    db.add(user)
    db.commit()
    db.refresh(user)

    report = DailyReport(
        user_id=user.id,
        check_type=CheckTypeEnum.NIGHT,
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    db.add(report)
    db.flush()
    user.current_report_id = report.id
    db.commit()

    status = DailyReportService.process_response(db, user, "Senti náusea")
    assert status == "EXPIRED"
