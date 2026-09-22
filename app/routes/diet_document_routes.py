from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import DietDocumentRead, DietDocumentUrl
from app.services.diet_document_service import DietDocumentService

router = APIRouter(tags=["Diet documents"])


@router.put(
    "/patients/{patient_id}",
    response_model=DietDocumentRead,
    status_code=status.HTTP_200_OK,
)
def upload_diet_document(
    patient_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="FILENAME_REQUIRED")
    content = file.file.read(settings.DIET_DOCUMENT_MAX_UPLOAD_BYTES + 1)
    return DietDocumentService(db).upload(
        actor=current_user,
        patient_id=patient_id,
        content=content,
        declared_content_type=file.content_type,
        original_filename=file.filename,
    )


@router.get("/patients/{patient_id}", response_model=DietDocumentRead | None)
def get_diet_document(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DietDocumentService(db).get_for_patient(current_user, patient_id)


@router.get("/patients/{patient_id}/view", response_model=DietDocumentUrl)
def get_diet_document_url(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DietDocumentUrl(
        url=DietDocumentService(db).signed_url(current_user, patient_id),
        expires_in=settings.DIET_DOCUMENT_SIGNED_URL_TTL_SECONDS,
    )


@router.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diet_document(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    DietDocumentService(db).delete(current_user, patient_id)
    return None
