from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    AiReportCache,
    AiReportStatusEnum,
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MonitoringPlan,
    User,
)
from app.models.schemas import CustomAiReportPreviewRequest
from app.services.custom_report_preview_service import CustomReportPreviewService


TOKEN_SECRET = "test-preview-secret-with-32-characters"


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def create_users_and_plan(db):
    patient = User(name="Paciente", email="paciente@example.com")
    professional = User(name="Profissional", email="profissional@example.com")
    db.add_all([patient, professional])
    db.commit()
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True)
    db.add(plan)
    db.commit()
    return patient, professional, plan


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


def create_cached_report(
    db,
    *,
    patient,
    professional,
    status: AiReportStatusEnum,
    generated_at: datetime | None = None,
    next_generation_at: datetime | None = None,
):
    report = AiReportCache(
        patient_id=patient.id,
        professional_user_id=professional.id,
        periodo="personalizado",
        modo="avaliacao_clinica",
        status=status.value,
        generated_at=generated_at,
        next_generation_at=next_generation_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def preview_payload(start_date: date, end_date: date) -> CustomAiReportPreviewRequest:
    return CustomAiReportPreviewRequest(start_date=start_date, end_date=end_date)


def test_preview_returns_signed_token_for_eligible_patient():
    db = build_session()
    patient, professional, plan = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=start_date)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    service = CustomReportPreviewService(db, TOKEN_SECRET)

    preview = service.preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
        now=now,
    )

    assert preview.eligibility.can_generate is True
    assert preview.modo == "avaliacao_clinica"
    assert preview.eligibility.reason is None
    assert preview.preview_token
    assert preview.preview_expires_at == now + timedelta(minutes=15)
    token_payload = service.decode_token(preview.preview_token, now=now)
    assert token_payload["patient_id"] == patient.id
    assert token_payload["requested_by_user_id"] == professional.id
    assert token_payload["start_date"] == start_date.isoformat()
    assert token_payload["end_date"] == end_date.isoformat()
    assert token_payload["summary_hash"] == service.summary_hash(preview.summary)


def test_preview_does_not_issue_token_when_data_is_insufficient():
    db = build_session()
    patient, professional, _ = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)

    preview = CustomReportPreviewService(db, TOKEN_SECRET).preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
    )

    assert preview.eligibility.can_generate is False
    assert preview.eligibility.reason == "INSUFFICIENT_DATA"
    assert preview.preview_token is None
    assert preview.preview_expires_at is None


def test_preview_applies_thirty_day_quota_per_patient():
    db = build_session()
    patient, professional, plan = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=start_date)
    now = datetime.now(timezone.utc)
    cached_report = create_cached_report(
        db,
        patient=patient,
        professional=professional,
        status=AiReportStatusEnum.COMPLETED,
        generated_at=now - timedelta(days=10),
        next_generation_at=now + timedelta(days=20),
    )

    preview = CustomReportPreviewService(db, TOKEN_SECRET).preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
        now=now,
    )

    assert preview.eligibility.can_generate is False
    assert preview.eligibility.reason == "PATIENT_MONTHLY_LIMIT_REACHED"
    assert preview.eligibility.latest_report_id == cached_report.id
    assert preview.eligibility.next_generation_at == cached_report.next_generation_at
    assert preview.preview_token is None


def test_preview_blocks_patient_with_report_in_progress():
    db = build_session()
    patient, professional, plan = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=start_date)
    create_cached_report(
        db,
        patient=patient,
        professional=professional,
        status=AiReportStatusEnum.PROCESSING,
    )

    preview = CustomReportPreviewService(db, TOKEN_SECRET).preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
    )

    assert preview.eligibility.can_generate is False
    assert preview.eligibility.reason == "REPORT_IN_PROGRESS"
    assert preview.preview_token is None


def test_preview_allows_new_generation_at_thirty_day_boundary():
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
        generated_at=now - timedelta(days=30),
        next_generation_at=now,
    )

    preview = CustomReportPreviewService(db, TOKEN_SECRET).preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
        now=now,
    )

    assert preview.eligibility.can_generate is True
    assert preview.preview_token


def test_preview_token_rejects_tampering_and_expiration():
    db = build_session()
    patient, professional, plan = create_users_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    create_completed_checkins(db, patient=patient, plan=plan, start_date=start_date)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    service = CustomReportPreviewService(db, TOKEN_SECRET)
    preview = service.preview(
        patient_id=patient.id,
        requested_by_user_id=professional.id,
        payload=preview_payload(start_date, end_date),
        now=now,
    )

    with pytest.raises(ValueError, match="Invalid preview token"):
        service.decode_token(preview.preview_token + "tampered", now=now)
    with pytest.raises(ValueError, match="Expired preview token"):
        service.decode_token(preview.preview_token, now=now + timedelta(minutes=15))
