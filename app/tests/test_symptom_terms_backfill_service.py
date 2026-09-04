from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
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
from app.services.symptom_terms_backfill_service import SymptomTermsBackfillService


class FakeInsightService:
    next_result: dict = {"termos": ["Cefaleia"]}

    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        return FakeInsightService.next_result


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def make_report(db, *, completed=True, had_symptoms=True, symptom_description="Dor de cabeça forte"):
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
        status=DailyReportStatusEnum.COMPLETED if completed else DailyReportStatusEnum.PENDING,
        completed=completed,
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


def test_pending_count_only_counts_completed_symptomatic_unlinked_reports(monkeypatch):
    db = build_session()
    unlinked = make_report(db)
    make_report(db, completed=False)
    make_report(db, had_symptoms=False, symptom_description=None)
    already_linked = make_report(db)
    term = SymptomTerm(label="Cefaleia")
    db.add(term)
    db.commit()
    db.refresh(term)
    db.add(DailyReportSymptomTerm(daily_report_id=already_linked.id, symptom_term_id=term.id, patient_id=already_linked.user_id))
    db.commit()

    service = SymptomTermsBackfillService(db)

    assert service.pending_count() == 1
    assert service._pending_query().all() == [unlinked]


def test_run_classifies_pending_reports_and_updates_linked_stat(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Cefaleia"]}

    db = build_session()
    report = make_report(db)
    service = SymptomTermsBackfillService(db)

    stats = service.run()

    assert stats.processed == 1
    assert stats.linked == 1
    assert service.pending_count() == 0
    linked_terms = db.query(SymptomTerm.label).join(
        DailyReportSymptomTerm, DailyReportSymptomTerm.symptom_term_id == SymptomTerm.id
    ).filter(DailyReportSymptomTerm.daily_report_id == report.id).all()
    assert [label for (label,) in linked_terms] == ["Cefaleia"]


def test_run_respects_max_records_and_is_restartable(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Cefaleia"]}

    db = build_session()
    make_report(db)
    make_report(db)
    make_report(db)
    service = SymptomTermsBackfillService(db)

    first_stats = service.run(max_records=2)
    assert first_stats.processed == 2
    assert service.pending_count() == 1

    second_stats = service.run(max_records=2)
    assert second_stats.processed == 1
    assert service.pending_count() == 0


def test_run_advances_past_reports_that_yield_no_terms(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": []}

    db = build_session()
    make_report(db)
    make_report(db)
    service = SymptomTermsBackfillService(db)

    stats = service.run(batch_size=1, max_records=2)

    assert stats.processed == 2
    assert stats.linked == 0


def test_reclassify_all_reprocesses_already_linked_reports_with_the_current_prompt(monkeypatch):
    # Simulates rolling out a prompt fix: a report already classified under
    # the old prompt (only "Refluxo") should get its links replaced once
    # reclassify_all re-runs it against the improved prompt.
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.symptom_normalization_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"termos": ["Refluxo"]}

    db = build_session()
    report = make_report(db, symptom_description="Refluxo, dor de cabeça")
    service = SymptomTermsBackfillService(db)
    service.run()

    linked_labels = db.query(SymptomTerm.label).join(
        DailyReportSymptomTerm, DailyReportSymptomTerm.symptom_term_id == SymptomTerm.id
    ).filter(DailyReportSymptomTerm.daily_report_id == report.id).all()
    assert [label for (label,) in linked_labels] == ["Refluxo"]

    # Nothing left "pending" the normal way -- reclassify_all is required
    # to touch it again.
    assert service.pending_count() == 0
    assert service.pending_count(reclassify_all=True) == 1

    FakeInsightService.next_result = {"termos": ["Refluxo", "Cefaleia"]}
    stats = service.run(reclassify_all=True)

    assert stats.processed == 1
    linked_labels = sorted(
        label
        for (label,) in db.query(SymptomTerm.label)
        .join(DailyReportSymptomTerm, DailyReportSymptomTerm.symptom_term_id == SymptomTerm.id)
        .filter(DailyReportSymptomTerm.daily_report_id == report.id)
        .all()
    )
    assert linked_labels == ["Cefaleia", "Refluxo"]
