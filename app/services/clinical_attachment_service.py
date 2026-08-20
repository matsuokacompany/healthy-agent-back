from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.access_policy import AccessPolicy
from app.core.config import settings
from app.core.permissions import has_role
from app.models.models import (
    ClinicalAttachment,
    ClinicalAttachmentSourceEnum,
    ClinicalAttachmentStatusEnum,
    DailyReport,
    RoleNameEnum,
    User,
)


class ClinicalAttachmentService:
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        actor: User,
        patient_id: int,
        content: bytes,
        declared_content_type: str | None,
        description: str | None = None,
        daily_report_id: int | None = None,
        source: ClinicalAttachmentSourceEnum | None = None,
        whatsapp_message_id: str | None = None,
        whatsapp_media_id: str | None = None,
    ) -> ClinicalAttachment:
        self._ensure_enabled(source)
        patient = AccessPolicy(self.db, actor).require_patient_read(patient_id)
        source = source or self._portal_source(actor, patient)
        self._validate_source_actor(source, actor, patient)

        if declared_content_type not in self.ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="UNSUPPORTED_IMAGE_TYPE")
        if not content or len(content) > settings.CLINICAL_IMAGE_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="IMAGE_TOO_LARGE")

        report = self._validate_report(patient.id, daily_report_id)
        self._enforce_quota(patient.id, report, source)
        normalized = self._normalize(content)

        attachment = ClinicalAttachment(
            patient_id=patient.id,
            uploaded_by_user_id=actor.id,
            monitoring_plan_id=report.monitoring_plan_id if report else None,
            daily_report_id=report.id if report else None,
            source=source.value,
            whatsapp_message_id=whatsapp_message_id,
            whatsapp_media_id=whatsapp_media_id,
            bucket=settings.SUPABASE_STORAGE_BUCKET,
            object_key="pending",
            content_type="image/jpeg",
            byte_size=len(normalized),
            sha256=sha256(normalized).hexdigest(),
            description=(description or "").strip()[:500] or None,
            status=ClinicalAttachmentStatusEnum.AVAILABLE.value,
        )
        self.db.add(attachment)
        self.db.flush()
        attachment.object_key = f"patients/{patient.supabase_user_id or patient.id}/attachments/{uuid4()}.jpg"

        try:
            self._upload(attachment.object_key, normalized)
            self.db.commit()
            self.db.refresh(attachment)
            return attachment
        except Exception:
            self.db.rollback()
            raise

    def list_for_patient(self, actor: User, patient_id: int) -> list[ClinicalAttachment]:
        AccessPolicy(self.db, actor).require_patient_read(patient_id)
        return (
            self.db.query(ClinicalAttachment)
            .filter(
                ClinicalAttachment.patient_id == patient_id,
                ClinicalAttachment.deleted_at.is_(None),
                ClinicalAttachment.status == ClinicalAttachmentStatusEnum.AVAILABLE.value,
            )
            .order_by(ClinicalAttachment.created_at.desc(), ClinicalAttachment.id.desc())
            .all()
        )

    def signed_url(self, actor: User, attachment_id: int) -> str:
        attachment = self._get_available(attachment_id)
        AccessPolicy(self.db, actor).require_patient_read(attachment.patient_id)
        self._ensure_storage_configured()
        encoded = quote(attachment.object_key, safe="/")
        response = httpx.post(
            f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1/object/sign/{attachment.bucket}/{encoded}",
            headers=self._storage_headers(),
            json={"expiresIn": settings.CLINICAL_IMAGE_SIGNED_URL_TTL_SECONDS},
            timeout=10.0,
        )
        response.raise_for_status()
        signed_path = response.json().get("signedURL") or response.json().get("signedUrl")
        if not signed_path:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="IMAGE_URL_UNAVAILABLE")
        if signed_path.startswith("http"):
            return signed_path
        return f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1{signed_path}"

    def delete(self, actor: User, attachment_id: int) -> None:
        attachment = self._get_available(attachment_id)
        AccessPolicy(self.db, actor).require_patient_read(attachment.patient_id)
        if actor.id not in {attachment.patient_id, attachment.uploaded_by_user_id}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATTACHMENT_DELETE_NOT_ALLOWED")
        attachment.status = ClinicalAttachmentStatusEnum.DELETED.value
        attachment.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        self._delete_object(attachment.bucket, attachment.object_key)

    def _validate_report(self, patient_id: int, report_id: int | None) -> DailyReport | None:
        if report_id is None:
            return None
        report = self.db.query(DailyReport).filter(DailyReport.id == report_id).first()
        if not report or report.user_id != patient_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DAILY_REPORT_NOT_FOUND")
        return report

    def _enforce_quota(self, patient_id: int, report: DailyReport | None, source: ClinicalAttachmentSourceEnum) -> None:
        active = self.db.query(ClinicalAttachment).filter(
            ClinicalAttachment.patient_id == patient_id,
            ClinicalAttachment.deleted_at.is_(None),
        )
        if active.count() >= settings.CLINICAL_IMAGE_MAX_STORED_PER_PATIENT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PATIENT_IMAGE_QUOTA_REACHED")
        if source == ClinicalAttachmentSourceEnum.WHATSAPP:
            if report is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="WHATSAPP_IMAGE_REQUIRES_REPORT")
            if active.filter(
                ClinicalAttachment.daily_report_id == report.id,
                ClinicalAttachment.source == ClinicalAttachmentSourceEnum.WHATSAPP.value,
            ).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="WHATSAPP_IMAGE_LIMIT_REACHED")

    @staticmethod
    def _normalize(content: bytes) -> bytes:
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > settings.CLINICAL_IMAGE_MAX_PIXELS:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="IMAGE_DIMENSIONS_TOO_LARGE")
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((settings.CLINICAL_IMAGE_MAX_DIMENSION,) * 2)
                output = BytesIO()
                image.save(output, format="JPEG", quality=settings.CLINICAL_IMAGE_JPEG_QUALITY, optimize=True)
                return output.getvalue()
        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="INVALID_IMAGE") from exc

    @staticmethod
    def _portal_source(actor: User, patient: User) -> ClinicalAttachmentSourceEnum:
        if actor.id == patient.id:
            return ClinicalAttachmentSourceEnum.PATIENT_PORTAL
        return ClinicalAttachmentSourceEnum.PROFESSIONAL_PORTAL

    @staticmethod
    def _validate_source_actor(source: ClinicalAttachmentSourceEnum, actor: User, patient: User) -> None:
        if source == ClinicalAttachmentSourceEnum.PATIENT_PORTAL and actor.id != patient.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_ATTACHMENT_SOURCE")
        if source == ClinicalAttachmentSourceEnum.PROFESSIONAL_PORTAL and not has_role(actor, RoleNameEnum.PROFESSIONAL):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_ATTACHMENT_SOURCE")
        if source == ClinicalAttachmentSourceEnum.WHATSAPP and actor.id != patient.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_ATTACHMENT_SOURCE")

    @staticmethod
    def _ensure_enabled(source: ClinicalAttachmentSourceEnum | None) -> None:
        if not settings.CLINICAL_IMAGES_ENABLED:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CLINICAL_IMAGE_UPLOADS_DISABLED")
        if source == ClinicalAttachmentSourceEnum.WHATSAPP:
            enabled = settings.WHATSAPP_CLINICAL_IMAGES_ENABLED
        else:
            enabled = settings.PORTAL_CLINICAL_IMAGES_ENABLED
        if not enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CLINICAL_IMAGE_UPLOADS_DISABLED")

    @staticmethod
    def _ensure_storage_configured() -> None:
        if not settings.SUPABASE_PROJECT_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CLINICAL_IMAGE_STORAGE_NOT_CONFIGURED")

    @classmethod
    def _storage_headers(cls) -> dict[str, str]:
        cls._ensure_storage_configured()
        return {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }

    @classmethod
    def _upload(cls, object_key: str, content: bytes) -> None:
        cls._ensure_storage_configured()
        encoded = quote(object_key, safe="/")
        response = httpx.post(
            f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{encoded}",
            headers={**cls._storage_headers(), "Content-Type": "image/jpeg", "x-upsert": "false"},
            content=content,
            timeout=30.0,
        )
        response.raise_for_status()

    @classmethod
    def _delete_object(cls, bucket: str, object_key: str) -> None:
        try:
            encoded = quote(object_key, safe="/")
            response = httpx.delete(
                f"{settings.SUPABASE_PROJECT_URL.rstrip('/')}/storage/v1/object/{bucket}/{encoded}",
                headers=cls._storage_headers(),
                timeout=10.0,
            )
            response.raise_for_status()
        except Exception:
            # The database deletion remains authoritative; operational cleanup can retry.
            pass

    def _get_available(self, attachment_id: int) -> ClinicalAttachment:
        attachment = self.db.query(ClinicalAttachment).filter(
            ClinicalAttachment.id == attachment_id,
            ClinicalAttachment.deleted_at.is_(None),
            ClinicalAttachment.status == ClinicalAttachmentStatusEnum.AVAILABLE.value,
        ).first()
        if not attachment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATTACHMENT_NOT_FOUND")
        return attachment
