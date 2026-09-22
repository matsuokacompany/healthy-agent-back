from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import PatientHandoffSummary
from app.services.patient_handoff_service import PatientHandoffService

router = APIRouter(tags=["Patient handoff summary"])


@router.get("/patients/{patient_id}", response_model=PatientHandoffSummary)
def get_patient_handoff_summary(
    patient_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientHandoffService(db).get_summary(
        current_user, patient_id, start_date=start_date, end_date=end_date
    )


@router.get("/me", response_model=PatientHandoffSummary)
def get_my_handoff_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientHandoffService(db).get_summary(
        current_user, current_user.id, start_date=start_date, end_date=end_date
    )
