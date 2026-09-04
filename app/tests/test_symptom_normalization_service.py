from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MonitoringPlan,
    SymptomTerm,
    User,
)
from app.services.symptom_normalization_service import SymptomNormalizationService


class FakeInsightService:
    last_prompt_input: str | None = None

    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        FakeInsightService.last_prompt_input = relatorio_texto
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


def create_patient_with_report(db, *, had_symptoms=True, symptom_description="Um pouco de diarréia"):
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
        had_symptoms=had_symptoms,
        symptom_description=symptom_description,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def linked_labels(db, report_id):
    rows = (
        db.query(SymptomTerm.label)
        .join(DailyReportSymptomTerm, DailyReportSymptomTerm.symptom_term_id == SymptomTerm.id)
        .filter(DailyReportSymptomTerm.daily_report_id == report_id)
        .all()
    )
    return sorted(label for (label,) in rows)


def test_normalize_reuses_existing_vocabulary_term(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Diarreia"]}

    db = build_session()
    db.add(SymptomTerm(label="Diarreia"))
    db.commit()
    report = create_patient_with_report(db, symptom_description="Um pouco de diarréia")

    SymptomNormalizationService.normalize(db, report, report.symptom_description)

    assert db.query(SymptomTerm).count() == 1
    assert linked_labels(db, report.id) == ["Diarreia"]
    assert "Um pouco de diarréia" in FakeInsightService.last_prompt_input
    assert "Diarreia" in FakeInsightService.last_prompt_input


def test_normalize_creates_new_term_when_nothing_fits(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Dor no cotovelo"]}

    db = build_session()
    report = create_patient_with_report(db, symptom_description="Dói o cotovelo esquerdo desde ontem")

    SymptomNormalizationService.normalize(db, report, report.symptom_description)

    assert linked_labels(db, report.id) == ["Dor no cotovelo"]
    assert db.query(SymptomTerm).filter(SymptomTerm.label == "Dor no cotovelo").count() == 1


def test_normalize_dedupes_repeated_and_case_variant_terms(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Cefaleia", "cefaleia", "Cefaleia"]}

    db = build_session()
    report = create_patient_with_report(db, symptom_description="Dor de cabeça forte")

    SymptomNormalizationService.normalize(db, report, report.symptom_description)

    assert linked_labels(db, report.id) == ["Cefaleia"]
    assert db.query(DailyReportSymptomTerm).filter(DailyReportSymptomTerm.daily_report_id == report.id).count() == 1


def test_normalize_replaces_prior_terms_on_reprocessing(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )

    db = build_session()
    report = create_patient_with_report(db, symptom_description="Dor de cabeça e febre")

    FakeInsightService.next_result = {"termos": ["Cefaleia", "Febre"]}
    SymptomNormalizationService.normalize(db, report, report.symptom_description)
    assert linked_labels(db, report.id) == ["Cefaleia", "Febre"]

    FakeInsightService.next_result = {"termos": ["Febre"]}
    SymptomNormalizationService.normalize(db, report, report.symptom_description)
    assert linked_labels(db, report.id) == ["Febre"]


def test_normalize_is_noop_without_symptoms(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Nao deveria rodar"]}

    db = build_session()
    report = create_patient_with_report(db, had_symptoms=False, symptom_description=None)

    SymptomNormalizationService.normalize(db, report, report.symptom_description)

    assert db.query(SymptomTerm).count() == 0
    assert db.query(DailyReportSymptomTerm).count() == 0


def test_normalize_is_noop_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    db = build_session()
    report = create_patient_with_report(db)

    SymptomNormalizationService.normalize(db, report, report.symptom_description)

    assert db.query(SymptomTerm).count() == 0
    assert db.query(DailyReportSymptomTerm).count() == 0


def test_normalize_swallows_provider_errors(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        RaisingInsightService,
    )

    db = build_session()
    report = create_patient_with_report(db)

    SymptomNormalizationService.normalize(db, report, report.symptom_description)  # must not raise

    assert db.query(SymptomTerm).count() == 0
    assert db.query(DailyReportSymptomTerm).count() == 0


def test_clear_removes_existing_term_links():
    db = build_session()
    term = SymptomTerm(label="Cefaleia")
    db.add(term)
    db.commit()
    db.refresh(term)
    report = create_patient_with_report(db, symptom_description="Dor de cabeça")
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=report.user_id))
    db.commit()

    SymptomNormalizationService.clear(db, report)

    assert linked_labels(db, report.id) == []
    # The shared vocabulary term itself is untouched, only the link row.
    assert db.query(SymptomTerm).count() == 1


def test_clear_is_a_noop_when_there_is_nothing_to_clear():
    db = build_session()
    report = create_patient_with_report(db, had_symptoms=False, symptom_description=None)

    SymptomNormalizationService.clear(db, report)  # must not raise

    assert linked_labels(db, report.id) == []


def test_normalize_recovers_the_session_after_a_failed_write_so_later_reports_still_work(monkeypatch):
    # A write-time failure partway through _normalize (e.g. a flush-time
    # IntegrityError) leaves the SQLAlchemy session in a "pending rollback"
    # state -- every later query on it raises PendingRollbackError until
    # someone calls db.rollback(). SymptomTermsBackfillService reuses the
    # same session across many reports in one run, so without recovering
    # here, one bad report would silently no-op every report processed
    # after it in that same batch. Using a real mapper-level event (rather
    # than monkeypatching Session.flush itself) so the failure goes through
    # SQLAlchemy's own flush machinery and actually reproduces the broken
    # session state, not just an exception that never touched it.
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )

    db = build_session()
    failing_report = create_patient_with_report(db, symptom_description="Sintoma A")
    healthy_report = create_patient_with_report(db, symptom_description="Sintoma B")
    failing_description = failing_report.symptom_description
    healthy_description = healthy_report.symptom_description
    failing_report_id, healthy_report_id = failing_report.id, healthy_report.id

    def fail_once_before_insert(_mapper, _connection, _target):
        event.remove(SymptomTerm, "before_insert", fail_once_before_insert)
        raise RuntimeError("simulated write failure")

    event.listen(SymptomTerm, "before_insert", fail_once_before_insert)
    FakeInsightService.next_result = {"termos": ["Termo Novo"]}

    SymptomNormalizationService.normalize(db, failing_report, failing_description)
    assert linked_labels(db, failing_report_id) == []

    FakeInsightService.next_result = {"termos": ["Outro Termo"]}
    SymptomNormalizationService.normalize(db, healthy_report, healthy_description)

    assert linked_labels(db, healthy_report_id) == ["Outro Termo"]
