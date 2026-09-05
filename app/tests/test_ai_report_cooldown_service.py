from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import AiReportCache, AiReportStatusEnum, User
from app.services.ai_report_cooldown_service import AiReportCooldownService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_report(db, *, mode="avaliacao_clinica", status=AiReportStatusEnum.COMPLETED):
    patient = User(name="Patient", email="patient@example.com")
    super_admin = User(name="Super Admin", email="admin@example.com")
    db.add_all([patient, super_admin])
    db.flush()
    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    report = AiReportCache(
        patient_id=patient.id,
        professional_user_id=super_admin.id,
        periodo="personalizado",
        modo=mode,
        status=status.value,
        generated_at=now - timedelta(days=11) if status == AiReportStatusEnum.COMPLETED else None,
        next_generation_at=now + timedelta(days=19) if status == AiReportStatusEnum.COMPLETED else None,
    )
    db.add(report)
    db.commit()
    return patient, super_admin, report, now


def test_release_once_expires_matching_cooldown():
    db = build_session()
    patient, super_admin, report, now = create_report(db)

    response = AiReportCooldownService(db).release_once(
        patient_id=patient.id,
        mode="avaliacao_clinica",
        released_by=super_admin,
        now=now,
    )

    db.refresh(report)
    # SQLite (this test's engine) drops tzinfo on DateTime(timezone=True)
    # round-trip even though the value written was UTC-aware -- same quirk
    # documented in payment_service.py's subscription_grants_access.
    next_generation_at = report.next_generation_at
    if next_generation_at.tzinfo is None:
        next_generation_at = next_generation_at.replace(tzinfo=timezone.utc)
    assert next_generation_at == now
    assert response.report_id == report.id
    previous_next_generation_at = response.previous_next_generation_at
    if previous_next_generation_at.tzinfo is None:
        previous_next_generation_at = previous_next_generation_at.replace(tzinfo=timezone.utc)
    assert previous_next_generation_at == now + timedelta(days=19)
    assert response.released_by_user_id == super_admin.id


def test_release_once_rejects_cooldown_that_is_already_released():
    db = build_session()
    patient, super_admin, report, now = create_report(db)
    report.next_generation_at = now
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        AiReportCooldownService(db).release_once(
            patient_id=patient.id,
            mode="avaliacao_clinica",
            released_by=super_admin,
            now=now,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "AI report cooldown is not active"


def test_release_once_rejects_when_report_is_in_progress():
    db = build_session()
    patient, super_admin, _, now = create_report(db, status=AiReportStatusEnum.PROCESSING)

    with pytest.raises(HTTPException) as exc_info:
        AiReportCooldownService(db).release_once(
            patient_id=patient.id,
            mode="avaliacao_clinica",
            released_by=super_admin,
            now=now,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "AI report already in progress"
