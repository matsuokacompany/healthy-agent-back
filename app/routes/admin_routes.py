from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_super_admin
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import (
    AdminBillingSummary,
    AdminCostEntryCreate,
    AdminCostEntryRead,
    AdminCostSummary,
    AdminSystemHealth,
    AdminUserRead,
    AdminUserStatusEnum,
    AdminWhatsappStats,
    AiReportCooldownReleaseRequest,
    AiReportCooldownReleaseResponse,
)
from app.services.admin_reporting_service import AdminReportingService
from app.services.ai_report_cooldown_service import AiReportCooldownService


router = APIRouter(tags=["Super Admin"])


@router.get("/users", response_model=list[AdminUserRead])
def list_admin_users(
    role: str | None = None,
    status: AdminUserStatusEnum | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).list_users(role=role, status=status, search=search)


@router.get("/billing/summary", response_model=AdminBillingSummary)
def get_admin_billing_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).billing_summary()


@router.get("/costs", response_model=AdminCostSummary)
def get_admin_costs(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).cost_summary(start_date=start_date, end_date=end_date)


@router.get("/costs/entries", response_model=list[AdminCostEntryRead])
def list_admin_cost_entries(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).list_cost_entries(start_date=start_date, end_date=end_date)


@router.post("/costs/entries", response_model=AdminCostEntryRead, status_code=201)
def create_admin_cost_entry(
    payload: AdminCostEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).create_cost_entry(current_user, payload)


@router.delete("/costs/entries/{entry_id}", status_code=204)
def delete_admin_cost_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    AdminReportingService(db).delete_cost_entry(entry_id)
    return None


@router.get("/whatsapp/stats", response_model=AdminWhatsappStats)
def get_admin_whatsapp_stats(
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).whatsapp_stats(days=days)


@router.get("/system/health", response_model=AdminSystemHealth)
def get_admin_system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AdminReportingService(db).system_health()


@router.post(
    "/patients/{patient_id}/ai-reports/release-cooldown",
    response_model=AiReportCooldownReleaseResponse,
)
def release_patient_ai_report_cooldown(
    patient_id: int,
    payload: AiReportCooldownReleaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return AiReportCooldownService(db).release_once(
        patient_id=patient_id,
        mode=payload.modo,
        released_by=current_user,
    )
