from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import (
    DailyReportStatusEnum,
    PatientDashboardCalendarResponse,
    PatientDashboardCheckinsResponse,
    PatientDashboardHistoryResponse,
    PatientDashboardResponseV2,
    PatientDashboardStatisticsResponse,
)
from app.services.patient_dashboard_service import PaginationParams, PatientDashboardService, ReportFilters

router = APIRouter(tags=["Patient Dashboard"])


@router.get("/dashboard", response_model=PatientDashboardResponseV2)
def get_patient_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientDashboardService(db).get_dashboard(current_user)


@router.get("/dashboard/history", response_model=PatientDashboardHistoryResponse)
def get_patient_dashboard_history(
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
    return PatientDashboardService(db).get_history(
        current_user,
        pagination=PaginationParams(page=page, per_page=per_page),
        filters=ReportFilters(
            start_date=start_date,
            end_date=end_date,
            status=status.value if status else None,
            had_symptoms=had_symptoms,
        ),
        order=order,
    )


@router.get("/dashboard/calendar", response_model=PatientDashboardCalendarResponse)
def get_patient_dashboard_calendar(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientDashboardService(db).get_calendar(current_user, year=year, month=month)


@router.get("/dashboard/statistics", response_model=PatientDashboardStatisticsResponse)
def get_patient_dashboard_statistics(
    period: Literal["7d", "30d", "90d", "1y"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientDashboardService(db).get_statistics(
        current_user,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/dashboard/checkins", response_model=PatientDashboardCheckinsResponse)
def get_patient_dashboard_checkins(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: DailyReportStatusEnum | None = None,
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientDashboardService(db).get_checkins(
        current_user,
        pagination=PaginationParams(page=page, per_page=per_page),
        filters=ReportFilters(status=status.value if status else None),
        order=order,
    )
