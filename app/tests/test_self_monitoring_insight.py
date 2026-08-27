from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    SelfMonitoringInsight,
    Subscription,
    SubscriptionStatusEnum,
    User,
)
from app.services.insight_service import InsightGenerationResult
from app.services.self_monitoring_service import SelfMonitoringService


class SuccessfulInsightService:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def gerar_interpretacao_com_uso(self, clinical_summary):
        return InsightGenerationResult(
            data={"resumo": "Evolução estável", "pontos_positivos": [], "pontos_de_atencao": [], "sugestao": "Converse com um profissional."},
            input_tokens=120,
            output_tokens=60,
        )


class FailingInsightService:
    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao_com_uso(self, clinical_summary):
        raise RuntimeError("provider unavailable")


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def create_patient_with_active_subscription(db):
    patient = User(name="Paciente Autonomo", email="autonomo@example.com", phone="5511999990000")
    db.add(patient)
    db.commit()
    plan = MonitoringPlan(
        patient_id=patient.id,
        title="Automonitoramento",
        active=True,
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
    )
    db.add(plan)
    db.add(Subscription(user_id=patient.id, status=SubscriptionStatusEnum.ACTIVE.value))
    db.commit()
    return patient, plan


def create_completed_checkins(db, *, patient, plan, start_date: date, total: int = 10):
    for offset in range(total):
        report_date = start_date + timedelta(days=offset)
        prompt_sent_at = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
        db.add(
            DailyReport(
                user_id=patient.id,
                monitoring_plan_id=plan.id,
                report_date=report_date,
                check_type=CheckTypeEnum.MORNING,
                status=DailyReportStatusEnum.COMPLETED,
                had_symptoms=False,
                completed=True,
                awaiting_response=False,
                awaiting_cause=False,
                prompt_sent_at=prompt_sent_at,
                expires_at=prompt_sent_at + timedelta(hours=24),
            )
        )
    db.commit()


def cost_kwargs(**overrides):
    values = {
        "api_key": "test-key",
        "model_name": "test-model",
        "max_input_tokens": 5000,
        "max_output_tokens": 500,
        "max_cost_usd": 1.0,
        "input_cost_per_million_usd": 1.0,
        "output_cost_per_million_usd": 2.0,
    }
    values.update(overrides)
    return values


def test_insight_blocked_without_subscription():
    db = build_session()
    patient = User(name="Sem assinatura", email="sem@example.com")
    db.add(patient)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        SelfMonitoringService(db).insight_report(patient, **cost_kwargs())

    assert exc_info.value.status_code == 402


def test_insight_reports_insufficient_data_without_calling_ai(monkeypatch):
    db = build_session()
    patient, _ = create_patient_with_active_subscription(db)
    monkeypatch.setattr(
        "app.services.self_monitoring_service.InsightService",
        FailingInsightService,
    )

    result = SelfMonitoringService(db).insight_report(patient, **cost_kwargs())

    assert result.sufficient_data is False
    assert result.insight is None
    assert db.query(SelfMonitoringInsight).count() == 0


def test_insight_generates_and_persists_summary(monkeypatch):
    db = build_session()
    patient, plan = create_patient_with_active_subscription(db)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=date.today() - timedelta(days=29))
    monkeypatch.setattr(
        "app.services.self_monitoring_service.InsightService",
        SuccessfulInsightService,
    )

    result = SelfMonitoringService(db).insight_report(patient, **cost_kwargs())

    assert result.sufficient_data is True
    assert result.insight["resumo"] == "Evolução estável"
    record = db.query(SelfMonitoringInsight).filter(SelfMonitoringInsight.patient_id == patient.id).one()
    assert record.input_tokens == 120
    assert record.output_tokens == 60
    assert record.next_generation_at == record.generated_at + timedelta(days=7)


def test_insight_reuses_cached_row_within_cooldown(monkeypatch):
    db = build_session()
    patient, plan = create_patient_with_active_subscription(db)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=date.today() - timedelta(days=29))
    now = datetime.now(timezone.utc)
    db.add(
        SelfMonitoringInsight(
            patient_id=patient.id,
            start_date=date.today() - timedelta(days=29),
            end_date=date.today(),
            insight_response={"resumo": "Cache existente"},
            generated_at=now - timedelta(days=1),
            next_generation_at=now + timedelta(days=6),
        )
    )
    db.commit()
    monkeypatch.setattr(
        "app.services.self_monitoring_service.InsightService",
        FailingInsightService,
    )

    result = SelfMonitoringService(db).insight_report(patient, **cost_kwargs())

    assert result.insight["resumo"] == "Cache existente"
    assert db.query(SelfMonitoringInsight).count() == 1


def test_insight_regenerates_after_cooldown_expires(monkeypatch):
    db = build_session()
    patient, plan = create_patient_with_active_subscription(db)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=date.today() - timedelta(days=29))
    now = datetime.now(timezone.utc)
    db.add(
        SelfMonitoringInsight(
            patient_id=patient.id,
            start_date=date.today() - timedelta(days=29),
            end_date=date.today(),
            insight_response={"resumo": "Cache antigo"},
            generated_at=now - timedelta(days=10),
            next_generation_at=now - timedelta(days=3),
        )
    )
    db.commit()
    monkeypatch.setattr(
        "app.services.self_monitoring_service.InsightService",
        SuccessfulInsightService,
    )

    result = SelfMonitoringService(db).insight_report(patient, **cost_kwargs(), now=now)

    assert result.insight["resumo"] == "Evolução estável"
    assert db.query(SelfMonitoringInsight).count() == 1


def test_insight_rejects_when_ai_not_configured():
    db = build_session()
    patient, plan = create_patient_with_active_subscription(db)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=date.today() - timedelta(days=29))

    with pytest.raises(HTTPException) as exc_info:
        SelfMonitoringService(db).insight_report(patient, **cost_kwargs(api_key=None))

    assert exc_info.value.status_code == 503


def test_insight_generation_failure_raises_and_does_not_persist(monkeypatch):
    db = build_session()
    patient, plan = create_patient_with_active_subscription(db)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=date.today() - timedelta(days=29))
    monkeypatch.setattr(
        "app.services.self_monitoring_service.InsightService",
        FailingInsightService,
    )

    with pytest.raises(HTTPException) as exc_info:
        SelfMonitoringService(db).insight_report(patient, **cost_kwargs())

    assert exc_info.value.status_code == 502
    assert db.query(SelfMonitoringInsight).count() == 0
