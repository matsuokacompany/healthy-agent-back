from datetime import date
from typing import Literal
import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import (
    AnamneseRead,
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
