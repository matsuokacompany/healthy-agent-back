from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.models import AiReportCache, AiReportStatusEnum, MonitoringProfessional, ProfessionalProfile
from app.models.schemas import CustomAiReportCreateRequest
from app.services.custom_report_generation_service import (
    CustomReportCostPolicy,
    CustomReportGenerationService,
)
from app.services.custom_report_preview_service import CustomReportPreviewService
from app.services.insight_service import InsightGenerationResult
from app.tests.test_custom_report_preview_service import (
    TOKEN_SECRET,
    build_session,
    create_cached_report,
    create_completed_checkins,
    create_users_and_plan,
    preview_payload,
)


class SuccessfulInsightService:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def gerar_interpretacao_com_uso(self, clinical_summary):
        return InsightGenerationResult(
            data={"avaliacao_clinica": {"hipotese_principal": "Hipótese"}},
            input_tokens=100,
            output_tokens=50,
        )


class FailingInsightService:
    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao_com_uso(self, clinical_summary):
        raise RuntimeError("provider unavailable")


def cost_policy(**overrides):
    values = {
        "model_name": "test-model",
        "max_input_tokens": 5000,
        "max_output_tokens": 500,
        "max_cost_usd": Decimal("1.00"),
        "input_cost_per_million_usd": Decimal("1.00"),
        "output_cost_per_million_usd": Decimal("2.00"),
    }
    values.update(overrides)
    return CustomReportCostPolicy(**values)


def eligible_context():
    db = build_session()
    patient, professional, plan = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=start_date)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    preview = CustomReportPreviewService(db, TOKEN_SECRET).preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
        now=now,
    )
    payload = CustomAiReportCreateRequest(
        start_date=start_date,
        end_date=end_date,
        modo="avaliacao_clinica",
        preview_token=preview.preview_token,
    )
    return db, patient, professional, payload, now


def test_generation_consumes_bonus_credit_when_cooldown_bypassed(monkeypatch):
    db = build_session()
    patient, professional, plan = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=start_date)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    create_cached_report(
        db,
        patient=patient,
        professional=professional,
        status=AiReportStatusEnum.COMPLETED,
        generated_at=now - timedelta(days=10),
        next_generation_at=now + timedelta(days=20),
    )
    professional_profile = ProfessionalProfile(user_id=professional.id, active=True)
    db.add(professional_profile)
    db.flush()
    link = MonitoringProfessional(
        monitoring_plan_id=plan.id,
        professional_profile_id=professional_profile.id,
        active=True,
        bonus_report_credits=1,
    )
    db.add(link)
    db.commit()

    preview = CustomReportPreviewService(db, TOKEN_SECRET).preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
        now=now,
    )
    assert preview.eligibility.used_bonus_credit is True
    payload = CustomAiReportCreateRequest(
        start_date=start_date,
        end_date=end_date,
        modo="avaliacao_clinica",
        preview_token=preview.preview_token,
    )
    monkeypatch.setattr(
        "app.services.custom_report_generation_service.InsightService",
        SuccessfulInsightService,
    )

    response = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(),
    ).generate(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=payload,
        now=now,
    )

    assert response.status == AiReportStatusEnum.COMPLETED
    db.refresh(link)
    assert link.bonus_report_credits == 0


def test_generation_completes_and_records_usage_cost_and_quota(monkeypatch):
    db, patient, professional, payload, now = eligible_context()
    monkeypatch.setattr(
        "app.services.custom_report_generation_service.InsightService",
        SuccessfulInsightService,
    )

    response = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(),
    ).generate(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=payload,
        now=now,
    )

    assert response.status == AiReportStatusEnum.COMPLETED
    assert response.input_tokens == 100
    assert response.output_tokens == 50
    assert response.actual_cost == 0.0002
    assert response.next_generation_at == response.generated_at + timedelta(days=30)
    report = db.query(AiReportCache).filter(AiReportCache.id == response.report_id).one()
    assert report.periodo == "personalizado"
    assert report.prompt_version == "custom-clinical-v1"
    assert report.failure_code is None


def test_generation_reuses_same_preview_token_without_second_ai_call(monkeypatch):
    db, patient, professional, payload, now = eligible_context()
    monkeypatch.setattr(
        "app.services.custom_report_generation_service.InsightService",
        SuccessfulInsightService,
    )
    service = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(),
    )

    first = service.generate(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=payload,
        now=now,
    )
    monkeypatch.setattr(
        "app.services.custom_report_generation_service.InsightService",
        FailingInsightService,
    )
    second = service.generate(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=payload,
        now=now,
    )

    assert second.report_id == first.report_id
    assert db.query(AiReportCache).count() == 1


def test_generation_rejects_token_that_does_not_match_requested_period():
    db, patient, professional, payload, now = eligible_context()
    mismatched_payload = CustomAiReportCreateRequest(
        start_date=payload.start_date - timedelta(days=1),
        end_date=payload.end_date,
        modo=payload.modo,
        preview_token=payload.preview_token,
    )
    service = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.generate(
            patient_id=patient.id,
            requested_by_user_id=professional.id,
            payload=mismatched_payload,
            now=now,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "PREVIEW_TOKEN_MISMATCH"
    assert db.query(AiReportCache).count() == 0


def test_generation_rejects_report_above_input_limit_before_persisting():
    db, patient, professional, payload, now = eligible_context()
    service = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(max_input_tokens=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.generate(
            patient_id=patient.id,
            requested_by_user_id=professional.id,
            payload=payload,
            now=now,
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == "REPORT_INPUT_TOO_LARGE"
    assert db.query(AiReportCache).count() == 0


def test_generation_rejects_report_above_cost_limit_before_persisting():
    db, patient, professional, payload, now = eligible_context()
    service = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(max_cost_usd=Decimal("0.000001")),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.generate(
            patient_id=patient.id,
            requested_by_user_id=professional.id,
            payload=payload,
            now=now,
        )

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "REPORT_COST_LIMIT_EXCEEDED"
    assert db.query(AiReportCache).count() == 0


def test_generation_marks_report_failed_without_consuming_quota(monkeypatch):
    db, patient, professional, payload, now = eligible_context()
    monkeypatch.setattr(
        "app.services.custom_report_generation_service.InsightService",
        FailingInsightService,
    )
    service = CustomReportGenerationService(
        db,
        token_secret=TOKEN_SECRET,
        api_key="test-key",
        cost_policy=cost_policy(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.generate(
            patient_id=patient.id,
            requested_by_user_id=professional.id,
            payload=payload,
            now=now,
        )

    assert exc_info.value.status_code == 502
    report = db.query(AiReportCache).one()
    assert report.status == AiReportStatusEnum.FAILED.value
    assert report.failure_code == "AI_GENERATION_FAILED"
    assert report.generated_at is None
    assert report.next_generation_at is None
