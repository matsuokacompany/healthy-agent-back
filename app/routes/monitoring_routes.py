from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin, get_current_user
from app.core.dependencies import get_db
from app.core.permissions import require_access_user
from app.models.models import User
from app.models.schemas import (
    MonitoringPlanCreate,
    MonitoringPlanRead,
    MonitoringPlanUpdate,
    MonitoringProfessionalCreate,
    MonitoringProfessionalRead,
    MonitoringProfessionalUpdate,
    ProfessionalProfileCreate,
    ProfessionalProfileRead,
    ProfessionalProfileUpdate,
)
from app.services.monitoring_service import MonitoringPlanService, ProfessionalProfileService

router = APIRouter(tags=["Monitoring"])


@router.post("/professional-profiles", response_model=ProfessionalProfileRead, status_code=status.HTTP_201_CREATED)
def create_professional_profile(
    payload: ProfessionalProfileCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return ProfessionalProfileService(db).create(payload)


@router.patch("/professional-profiles/{profile_id}", response_model=ProfessionalProfileRead)
def update_professional_profile(
    profile_id: int,
    payload: ProfessionalProfileUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return ProfessionalProfileService(db).update(profile_id, payload)


@router.post("/plans", response_model=MonitoringPlanRead, status_code=status.HTTP_201_CREATED)
def create_monitoring_plan(
    payload: MonitoringPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_access_user(current_user, payload.patient_id)
    return MonitoringPlanService(db).create(payload)


@router.get("/patients/{patient_id}/plans", response_model=list[MonitoringPlanRead])
def list_patient_monitoring_plans(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_access_user(current_user, patient_id)
    return MonitoringPlanService(db).list_for_patient(patient_id)


@router.patch("/plans/{plan_id}", response_model=MonitoringPlanRead)
def update_monitoring_plan(
    plan_id: int,
    payload: MonitoringPlanUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return MonitoringPlanService(db).update(plan_id, payload)


@router.post("/plans/{plan_id}/professionals", response_model=MonitoringProfessionalRead, status_code=status.HTTP_201_CREATED)
def add_professional_to_plan(
    plan_id: int,
    payload: MonitoringProfessionalCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return MonitoringPlanService(db).add_professional(plan_id, payload)


@router.patch("/plan-professionals/{link_id}", response_model=MonitoringProfessionalRead)
def update_plan_professional_link(
    link_id: int,
    payload: MonitoringProfessionalUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return MonitoringPlanService(db).update_professional(link_id, payload)
