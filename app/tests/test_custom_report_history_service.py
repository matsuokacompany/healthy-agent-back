from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.models import AiReportCache, AiReportStatusEnum, User
from app.services.custom_report_history_service import CustomReportHistoryService
from app.services.patient_dashboard_service import PaginationParams
from app.tests.test_custom_report_preview_service import build_session


def create_users(db):
    patient = User(name="Paciente", email="paciente@example.com")
    other_patient = User(name="Outro", email="outro@example.com")
    professional = User(name="Profissional", email="profissional@example.com")
    db.add_all([patient, other_patient, professional])
    db.commit()
    return patient, other_patient, professional


def create_report(
    db,
    *,
    patient,
    professional,
    requested_at: datetime,
    report_status: AiReportStatusEnum = AiReportStatusEnum.COMPLETED,
    periodo: str = "personalizado",
):
    report = AiReportCache(
        patient_id=patient.id,
        professional_user_id=professional.id,
        periodo=periodo,
        modo="avaliacao_clinica",
        start_date=date.today() - timedelta(days=29) if periodo == "personalizado" else None,
        end_date=date.today() if periodo == "personalizado" else None,
        status=report_status.value,
        requested_at=requested_at,
        generated_at=requested_at if report_status == AiReportStatusEnum.COMPLETED else None,
        clinical_summary="Resumo" if report_status == AiReportStatusEnum.COMPLETED else None,
        ai_response={"resultado": "ok"} if report_status == AiReportStatusEnum.COMPLETED else None,
        estimated_cost=Decimal("0.001"),
        actual_cost=Decimal("0.0008") if report_status == AiReportStatusEnum.COMPLETED else None,
        model_name="test-model",
        failure_code="AI_GENERATION_FAILED" if report_status == AiReportStatusEnum.FAILED else None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_history_lists_only_custom_reports_for_patient_with_pagination():
    db = build_session()
    patient, other_patient, professional = create_users(db)
    now = datetime.now(timezone.utc)
    oldest = create_report(db, patient=patient, professional=professional, requested_at=now - timedelta(days=3))
    middle = create_report(db, patient=patient, professional=professional, requested_at=now - timedelta(days=2))
    newest = create_report(db, patient=patient, professional=professional, requested_at=now - timedelta(days=1))
    create_report(db, patient=other_patient, professional=professional, requested_at=now)
    create_report(db, patient=patient, professional=professional, requested_at=now, periodo="mensal")

    first_page = CustomReportHistoryService(db).list_reports(
        patient.id,
        pagination=PaginationParams(page=1, per_page=2),
    )
    second_page = CustomReportHistoryService(db).list_reports(
        patient.id,
        pagination=PaginationParams(page=2, per_page=2),
    )

    assert [item.report_id for item in first_page.items] == [newest.id, middle.id]
    assert [item.report_id for item in second_page.items] == [oldest.id]
    assert first_page.pagination.total == 3
    assert first_page.pagination.total_pages == 2


def test_history_filters_by_status():
    db = build_session()
    patient, _, professional = create_users(db)
    now = datetime.now(timezone.utc)
    create_report(db, patient=patient, professional=professional, requested_at=now)
    failed = create_report(
        db,
        patient=patient,
        professional=professional,
        requested_at=now - timedelta(days=1),
        report_status=AiReportStatusEnum.FAILED,
    )

    response = CustomReportHistoryService(db).list_reports(
        patient.id,
        pagination=PaginationParams(),
        report_status=AiReportStatusEnum.FAILED.value,
    )

    assert [item.report_id for item in response.items] == [failed.id]
    assert response.items[0].failure_code == "AI_GENERATION_FAILED"


def test_history_detail_returns_full_result_and_costs():
    db = build_session()
    patient, _, professional = create_users(db)
    report = create_report(
        db,
        patient=patient,
        professional=professional,
        requested_at=datetime.now(timezone.utc),
    )

    detail = CustomReportHistoryService(db).get_report(patient.id, report.id)

    assert detail.report_id == report.id
    assert detail.clinical_summary == "Resumo"
    assert detail.ai == {"resultado": "ok"}
    assert detail.estimated_cost == 0.001
    assert detail.actual_cost == 0.0008


def test_history_detail_does_not_expose_another_patient_report():
    db = build_session()
    patient, other_patient, professional = create_users(db)
    report = create_report(
        db,
        patient=other_patient,
        professional=professional,
        requested_at=datetime.now(timezone.utc),
    )

    with pytest.raises(HTTPException) as exc_info:
        CustomReportHistoryService(db).get_report(patient.id, report.id)

    assert exc_info.value.status_code == 404
