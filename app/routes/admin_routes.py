from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_super_admin
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import AiReportCooldownReleaseRequest, AiReportCooldownReleaseResponse
from app.services.ai_report_cooldown_service import AiReportCooldownService


router = APIRouter(tags=["Super Admin"])


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
