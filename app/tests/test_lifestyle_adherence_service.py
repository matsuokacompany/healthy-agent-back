from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    User,
)
from app.services.lifestyle_adherence_service import LifestyleAdherenceService


class FakeInsightService:
    next_result: dict = {}

    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        return FakeInsightService.next_result


class RaisingInsightService:
    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        raise RuntimeError("provider unavailable")


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def create_self_service_report(db, *, lifestyle_notes="Segui a dieta e tomei os remédios"):
    user = User(name="Paciente", email=f"p-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    plan = MonitoringPlan(
        patient_id=user.id,
        title="Plano",
        active=True,
        start_date=date.today(),
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    now = datetime.now(timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        had_symptoms=False,
        lifestyle_notes=lifestyle_notes,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_classify_sets_both_fields_from_the_combined_reply(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.lifestyle_adherence_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"seguiu_dieta": True, "tomou_remedios": False}

    db = build_session()
    report = create_self_service_report(db, lifestyle_notes="Segui certinho mas esqueci o remédio de noite")

    LifestyleAdherenceService.classify(db, report, report.lifestyle_notes)

    db.refresh(report)
    assert report.diet_adherence is True
    assert report.medication_adherence is False


def test_classify_leaves_a_field_unset_when_the_model_returns_null(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.lifestyle_adherence_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"seguiu_dieta": True, "tomou_remedios": None}

    db = build_session()
    report = create_self_service_report(db, lifestyle_notes="Segui certinho")

    LifestyleAdherenceService.classify(db, report, report.lifestyle_notes)

    db.refresh(report)
    assert report.diet_adherence is True
    assert report.medication_adherence is None


def test_classify_is_noop_without_text():
    db = build_session()
    report = create_self_service_report(db, lifestyle_notes=None)

    LifestyleAdherenceService.classify(db, report, None)  # must not raise

    db.refresh(report)
    assert report.diet_adherence is None
    assert report.medication_adherence is None


def test_classify_is_noop_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    db = build_session()
    report = create_self_service_report(db)

    LifestyleAdherenceService.classify(db, report, report.lifestyle_notes)

    db.refresh(report)
    assert report.diet_adherence is None
    assert report.medication_adherence is None


def test_classify_swallows_provider_errors(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.lifestyle_adherence_service.InsightService",
        RaisingInsightService,
    )

    db = build_session()
    report = create_self_service_report(db)

    LifestyleAdherenceService.classify(db, report, report.lifestyle_notes)  # must not raise

    db.refresh(report)
    assert report.diet_adherence is None
    assert report.medication_adherence is None


def test_classify_recovers_the_session_after_a_failed_write_so_later_reports_still_work(monkeypatch):
    # Same session-rollback hazard as SymptomNormalizationService (see
    # test_symptom_normalization_service.py): a write-time failure partway
    # through classification must not leave the session unusable for the
    # next report processed in the same batch/run.
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.lifestyle_adherence_service.InsightService",
        FakeInsightService,
    )

    db = build_session()
    failing_report = create_self_service_report(db, lifestyle_notes="Relato A")
    healthy_report = create_self_service_report(db, lifestyle_notes="Relato B")

    def fail_once_before_update(_mapper, _connection, _target):
        event.remove(DailyReport, "before_update", fail_once_before_update)
        raise RuntimeError("simulated write failure")

    event.listen(DailyReport, "before_update", fail_once_before_update)
    FakeInsightService.next_result = {"seguiu_dieta": True, "tomou_remedios": True}

    LifestyleAdherenceService.classify(db, failing_report, failing_report.lifestyle_notes)
    db.refresh(failing_report)
    assert failing_report.diet_adherence is None

    LifestyleAdherenceService.classify(db, healthy_report, healthy_report.lifestyle_notes)
    db.refresh(healthy_report)
    assert healthy_report.diet_adherence is True
    assert healthy_report.medication_adherence is True
