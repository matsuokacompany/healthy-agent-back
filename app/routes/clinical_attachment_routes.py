from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import ClinicalAttachmentRead, ClinicalAttachmentUrl
from app.services.clinical_attachment_service import ClinicalAttachmentService


router = APIRouter(tags=["Clinical attachments"])


@router.post(
    "/patients/{patient_id}",
    response_model=list[ClinicalAttachmentRead],
    status_code=status.HTTP_201_CREATED,
)
def upload_clinical_images(
    patient_id: int,
    files: list[UploadFile] = File(...),
    description: str | None = Form(default=None, max_length=500),
    daily_report_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not files or len(files) > settings.CLINICAL_IMAGE_MAX_PORTAL_BATCH:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="IMAGE_BATCH_LIMIT_EXCEEDED")
    service = ClinicalAttachmentService(db)
    created = []
    for upload in files:
        content = upload.file.read(settings.CLINICAL_IMAGE_MAX_UPLOAD_BYTES + 1)
        created.append(
            service.create(
                actor=current_user,
                patient_id=patient_id,
                content=content,
                declared_content_type=upload.content_type,
                description=description,
                daily_report_id=daily_report_id,
            )
        )
    return created


@router.get("/patients/{patient_id}", response_model=list[ClinicalAttachmentRead])
def list_clinical_images(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ClinicalAttachmentService(db).list_for_patient(current_user, patient_id)


@router.get("/{attachment_id}/view", response_model=ClinicalAttachmentUrl)
def get_clinical_image_url(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ClinicalAttachmentUrl(
        url=ClinicalAttachmentService(db).signed_url(current_user, attachment_id),
        expires_in=settings.CLINICAL_IMAGE_SIGNED_URL_TTL_SECONDS,
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clinical_image(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ClinicalAttachmentService(db).delete(current_user, attachment_id)
    return None
