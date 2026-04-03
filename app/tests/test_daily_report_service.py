from datetime import date, datetime, timedelta, timezone

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

    report = DailyReport(
        user_id=user.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        had_symptoms=True,
    )
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
        report_date=date.today(),
        check_type=CheckTypeEnum.NIGHT,
        had_symptoms=True,
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    db.add(report)
    db.flush()
    user.current_report_id = report.id
    db.commit()

    status = DailyReportService.process_response(db, user, "Senti náusea")
    assert status == "EXPIRED"


def test_daily_report_pending_negative_creates_completed_report():
    db = build_session()
    user = User(
        name="Teste",
        email="pending-negative@example.com",
        telegram_id="111",
        pending_check_type=CheckTypeEnum.MORNING,
        pending_report_date=date.today(),
        pending_prompt_sent_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    status = DailyReportService.process_response(db, user, "Não tive sintomas")
    assert status == "NEGATIVE"

    report = db.query(DailyReport).filter(DailyReport.user_id == user.id).first()
    assert report is not None
    assert report.completed is True
    assert report.had_symptoms is False
    assert report.symptom_description is None

    db.refresh(user)
    assert user.current_report_id is None
    assert user.pending_check_type is None
    assert user.pending_report_date is None
    assert user.pending_prompt_sent_at is None


def test_daily_report_pending_positive_creates_report_and_asks_cause():
    db = build_session()
    user = User(
        name="Teste",
        email="pending-positive@example.com",
        telegram_id="222",
        pending_check_type=CheckTypeEnum.NIGHT,
        pending_report_date=date.today(),
        pending_prompt_sent_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    status = DailyReportService.process_response(db, user, "Tive dor de cabeça")
    assert status == "ASK_CAUSE"

    db.refresh(user)
    assert user.current_report_id is not None
    assert user.pending_check_type is None

    report = db.query(DailyReport).filter(DailyReport.id == user.current_report_id).first()
    assert report is not None
    assert report.had_symptoms is True
    assert report.symptom_description == "Tive dor de cabeça"


def test_daily_report_pending_expired_returns_expired_and_clears_pending():
    db = build_session()
    user = User(
        name="Teste",
        email="pending-expired@example.com",
        telegram_id="333",
        pending_check_type=CheckTypeEnum.NIGHT,
        pending_report_date=date.today(),
        pending_prompt_sent_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    status = DailyReportService.process_response(db, user, "Tive febre")
    assert status == "EXPIRED"

    db.refresh(user)
    assert user.current_report_id is None
    assert user.pending_check_type is None
    assert user.pending_report_date is None
    assert user.pending_prompt_sent_at is None
