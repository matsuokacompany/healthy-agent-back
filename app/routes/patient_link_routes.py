from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import PatientLinkRequestIncomingRead, PatientLinkRequestRead, PatientLinkRequestRespond
from app.services.patient_link_service import PatientLinkService

router = APIRouter(tags=["Patient Link Requests"])


@router.get("", response_model=list[PatientLinkRequestIncomingRead])
def list_incoming_link_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientLinkService(db).list_incoming_requests(current_user)


@router.post("/{request_id}/respond", response_model=PatientLinkRequestRead)
def respond_link_request(
    request_id: int,
    payload: PatientLinkRequestRespond,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PatientLinkService(db).respond(current_user, request_id, payload.accept)
