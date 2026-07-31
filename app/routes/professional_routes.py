from datetime import date
from typing import Literal
import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import (
    AnamneseRead,
    CustomAiReportPreviewRequest,
    CustomAiReportPreviewResponse,
    CustomAiReportCreateRequest,
    CustomAiReportResponse,
    CustomAiReportListResponse,
    AiReportStatusEnum,
    DailyReportStatusEnum,
    PatientDashboardCheckinsResponse,
    PatientDashboardResponseV2,
    ProfessionalAiReportRequest,
    ProfessionalAiReportResponse,
    ProfessionalPatientRead,
)
from app.services.patient_dashboard_service import PaginationParams, ReportFilters
from app.services.professional_service import ProfessionalService

router = APIRouter(tags=["Professional"])


@router.get("/patients", response_model=list[ProfessionalPatientRead])
def list_professional_patients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).list_patients(current_user)


@router.get("/patients/{patient_id}/dashboard", response_model=PatientDashboardResponseV2)
def get_professional_patient_dashboard(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).get_dashboard(current_user, patient_id)


@router.get("/patients/{patient_id}/checkins", response_model=PatientDashboardCheckinsResponse)
def get_professional_patient_checkins(
    patient_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    status: DailyReportStatusEnum | None = None,
    had_symptoms: bool | None = None,
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).get_checkins(
        current_user,
        patient_id,
        pagination=PaginationParams(page=page, per_page=per_page),
        filters=ReportFilters(
            start_date=start_date,
            end_date=end_date,
            status=status.value if status else None,
            had_symptoms=had_symptoms,
        ),
        order=order,
    )


@router.get("/patients/{patient_id}/anamnese", response_model=AnamneseRead)
def get_professional_patient_anamnese(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).get_anamnese(current_user, patient_id)


@router.post("/patients/{patient_id}/ai-report", response_model=ProfessionalAiReportResponse)
def generate_professional_patient_ai_report(
    patient_id: int,
    payload: ProfessionalAiReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).generate_ai_report(
        current_user,
        patient_id,
        periodo=payload.periodo,
        modo=payload.modo,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


@router.post(
    "/patients/{patient_id}/ai-reports/preview",
    response_model=CustomAiReportPreviewResponse,
)
def preview_professional_patient_ai_report(
    patient_id: int,
    payload: CustomAiReportPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).preview_custom_ai_report(
        current_user,
        patient_id,
        payload=payload,
        token_secret=settings.AI_REPORT_PREVIEW_SECRET,
    )


@router.post(
    "/patients/{patient_id}/ai-reports",
    response_model=CustomAiReportResponse,
)
def generate_custom_professional_patient_ai_report(
    patient_id: int,
    payload: CustomAiReportCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).generate_custom_ai_report(
        current_user,
        patient_id,
        payload=payload,
        token_secret=settings.AI_REPORT_PREVIEW_SECRET,
        api_key=settings.OPENAI_API_KEY,
        model_name=settings.AI_REPORT_MODEL,
        max_input_tokens=settings.AI_REPORT_MAX_INPUT_TOKENS,
        max_output_tokens=settings.AI_REPORT_MAX_OUTPUT_TOKENS,
        max_cost_usd=settings.AI_REPORT_MAX_COST_USD,
        input_cost_per_million_usd=settings.AI_REPORT_INPUT_COST_PER_MILLION_USD,
        output_cost_per_million_usd=settings.AI_REPORT_OUTPUT_COST_PER_MILLION_USD,
    )


@router.get(
    "/patients/{patient_id}/ai-reports",
    response_model=CustomAiReportListResponse,
)
def list_custom_professional_patient_ai_reports(
    patient_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    report_status: AiReportStatusEnum | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).list_custom_ai_reports(
        current_user,
        patient_id,
        pagination=PaginationParams(page=page, per_page=per_page),
        report_status=report_status.value if report_status else None,
    )


@router.get(
    "/patients/{patient_id}/ai-reports/{report_id}",
    response_model=CustomAiReportResponse,
)
def get_custom_professional_patient_ai_report(
    patient_id: int,
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProfessionalService(db).get_custom_ai_report(
        current_user,
        patient_id,
        report_id,
    )
