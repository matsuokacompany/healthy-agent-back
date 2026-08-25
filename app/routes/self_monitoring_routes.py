from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import CustomClinicalSummary, MonitoringPlanRead
from app.services.self_monitoring_service import SelfMonitoringService

router = APIRouter(tags=["Self Monitoring"])


@router.post("/plan", response_model=MonitoringPlanRead, status_code=status.HTTP_201_CREATED)
def create_or_reactivate_self_monitoring_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).create_or_reactivate_plan(current_user)


@router.get("/evolution-report", response_model=CustomClinicalSummary)
def get_self_monitoring_evolution_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).evolution_report(
        current_user,
        start_date=start_date,
        end_date=end_date,
    )
