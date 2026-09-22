from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.access_policy import AccessPolicy
from app.core.config import settings
from app.models.models import DietDocument, User
from app.services.supabase_storage import SupabaseStorageClient


class DietDocumentService:
    """At most one active diet-plan PDF per patient -- uploading a new one
    replaces the previous file and row rather than accumulating a gallery
    (see DietDocument's docstring in app/models/models.py)."""

    ALLOWED_MIME_TYPE = "application/pdf"

    def __init__(self, db: Session):
        self.db = db

    def upload(
        self,
        *,
        actor: User,
        patient_id: int,
        content: bytes,
        declared_content_type: str | None,
        original_filename: str,
    ) -> DietDocument:
        self._ensure_enabled()
        patient = AccessPolicy(self.db, actor).require_patient_read(patient_id)

        if declared_content_type != self.ALLOWED_MIME_TYPE:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="UNSUPPORTED_DOCUMENT_TYPE")
        if not content or len(content) > settings.DIET_DOCUMENT_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="DOCUMENT_TOO_LARGE")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="INVALID_PDF")

        storage = SupabaseStorageClient(settings.DIET_DOCUMENTS_BUCKET)
        object_key = f"patients/{patient.supabase_user_id or patient.id}/diet-plan/{uuid4()}.pdf"
        storage.upload(object_key, content, self.ALLOWED_MIME_TYPE)

        existing = self.db.query(DietDocument).filter(DietDocument.patient_id == patient.id).first()
        previous_object_key = existing.object_key if existing else None

        if existing:
            existing.uploaded_by_user_id = actor.id
            existing.bucket = settings.DIET_DOCUMENTS_BUCKET
            existing.object_key = object_key
            existing.original_filename = original_filename[:255]
            existing.byte_size = len(content)
            existing.sha256 = sha256(content).hexdigest()
            document = existing
        else:
            document = DietDocument(
                patient_id=patient.id,
                uploaded_by_user_id=actor.id,
                bucket=settings.DIET_DOCUMENTS_BUCKET,
                object_key=object_key,
                original_filename=original_filename[:255],
                byte_size=len(content),
                sha256=sha256(content).hexdigest(),
            )
            self.db.add(document)

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            storage.delete(object_key)
            raise
        self.db.refresh(document)

        if previous_object_key:
            storage.delete(previous_object_key)

        return document

    def get_for_patient(self, actor: User, patient_id: int) -> DietDocument | None:
        AccessPolicy(self.db, actor).require_patient_read(patient_id)
        return self.db.query(DietDocument).filter(DietDocument.patient_id == patient_id).first()

    def signed_url(self, actor: User, patient_id: int) -> str:
        document = self._get_or_404(actor, patient_id)
        return SupabaseStorageClient(document.bucket).sign_url(
            document.object_key, settings.DIET_DOCUMENT_SIGNED_URL_TTL_SECONDS
        )

    def delete(self, actor: User, patient_id: int) -> None:
        document = self._get_or_404(actor, patient_id)
        self.db.delete(document)
        self.db.commit()
        SupabaseStorageClient(document.bucket).delete(document.object_key)

    def _get_or_404(self, actor: User, patient_id: int) -> DietDocument:
        AccessPolicy(self.db, actor).require_patient_read(patient_id)
        document = self.db.query(DietDocument).filter(DietDocument.patient_id == patient_id).first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DIET_DOCUMENT_NOT_FOUND")
        return document

    @staticmethod
    def _ensure_enabled() -> None:
        if not settings.DIET_DOCUMENTS_ENABLED:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DIET_DOCUMENT_UPLOADS_DISABLED")
