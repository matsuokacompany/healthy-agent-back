from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import PatientDashboardResponse
from app.services.patient_dashboard_service import PatientDashboardService

router = APIRouter(tags=["Patient Dashboard"])


@router.get("/dashboard", response_model=PatientDashboardResponse)
def get_patient_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientDashboardService(db).get_dashboard(current_user)
