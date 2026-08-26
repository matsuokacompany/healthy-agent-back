import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from app.models.models import AiReportCache, AiReportStatusEnum
from app.models.schemas import (
    CustomAiReportEligibility,
    CustomAiReportPreviewRequest,
    CustomAiReportPreviewResponse,
    CustomClinicalSummary,
)
from app.services.custom_report_service import CustomReportService
from app.services.patient_link_service import find_link_with_bonus_credit


class CustomReportPreviewService:
    PREVIEW_TOKEN_TTL_MINUTES = 15
    MINIMUM_TOKEN_SECRET_LENGTH = 32

    def __init__(self, db: Session, token_secret: str):
        if not token_secret or len(token_secret) < self.MINIMUM_TOKEN_SECRET_LENGTH:
            raise ValueError("AI_REPORT_PREVIEW_SECRET must contain at least 32 characters")
        self.db = db
        self.token_secret = token_secret.encode("utf-8")

    def preview(
        self,
        *,
        patient_id: int,
        requested_by_user_id: int,
        payload: CustomAiReportPreviewRequest,
        now: datetime | None = None,
    ) -> CustomAiReportPreviewResponse:
        now = now or datetime.now(timezone.utc)
        summary = CustomReportService(self.db).build_summary(
            patient_id,
            payload.start_date,
            payload.end_date,
        )
        eligibility = self._build_eligibility(patient_id, requested_by_user_id, payload.modo, summary, now)
        if not eligibility.can_generate:
            return CustomAiReportPreviewResponse(
                modo=payload.modo,
                eligibility=eligibility,
                summary=summary,
            )

        expires_at = now + timedelta(minutes=self.PREVIEW_TOKEN_TTL_MINUTES)
        preview_token = self._encode_token(
            {
                "purpose": "custom_ai_report_preview",
                "patient_id": patient_id,
                "requested_by_user_id": requested_by_user_id,
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat(),
                "modo": payload.modo,
                "summary_hash": self.summary_hash(summary),
                "exp": int(expires_at.timestamp()),
            }
        )
        return CustomAiReportPreviewResponse(
            modo=payload.modo,
            eligibility=eligibility,
            summary=summary,
            preview_token=preview_token,
            preview_expires_at=expires_at,
        )

    def _build_eligibility(
        self,
        patient_id: int,
        requested_by_user_id: int,
        modo: str,
        summary: CustomClinicalSummary,
        now: datetime,
    ) -> CustomAiReportEligibility:
        active_report = (
            self.db.query(AiReportCache)
            .filter(AiReportCache.patient_id == patient_id)
            .filter(AiReportCache.status.in_([AiReportStatusEnum.PENDING.value, AiReportStatusEnum.PROCESSING.value]))
            .order_by(AiReportCache.requested_at.desc(), AiReportCache.id.desc())
            .first()
        )
        latest_report = (
            self.db.query(AiReportCache)
            .filter(AiReportCache.patient_id == patient_id)
            .filter(AiReportCache.modo == modo)
            .filter(AiReportCache.status == AiReportStatusEnum.COMPLETED.value)
            .filter(AiReportCache.generated_at.is_not(None))
            .order_by(AiReportCache.generated_at.desc(), AiReportCache.id.desc())
            .first()
        )

        next_generation_at = None
        if latest_report:
            next_generation_at = latest_report.next_generation_at or (
                latest_report.generated_at + timedelta(days=30)
            )

        reason = None
        used_bonus_credit = False
        if active_report:
            reason = "REPORT_IN_PROGRESS"
        elif next_generation_at and self._as_utc(next_generation_at) > self._as_utc(now):
            if find_link_with_bonus_credit(self.db, patient_id=patient_id, professional_user_id=requested_by_user_id):
                used_bonus_credit = True
            else:
                reason = "PATIENT_MONTHLY_LIMIT_REACHED"
        elif not summary.sufficient_data:
            reason = "INSUFFICIENT_DATA"

        return CustomAiReportEligibility(
            can_generate=reason is None,
            reason=reason,
            next_generation_at=next_generation_at,
            sufficient_data=summary.sufficient_data,
            completed_checkins=summary.metrics.completed_checkins,
            minimum_required=summary.minimum_completed_checkins,
            latest_report_id=latest_report.id if latest_report else None,
            last_generated_at=latest_report.generated_at if latest_report else None,
            used_bonus_credit=used_bonus_credit,
        )

    def decode_token(self, token: str, now: datetime | None = None) -> dict:
        try:
            encoded_payload, encoded_signature = token.split(".", maxsplit=1)
            expected_signature = hmac.new(
                self.token_secret,
                encoded_payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
            supplied_signature = self._base64url_decode(encoded_signature)
            if not hmac.compare_digest(expected_signature, supplied_signature):
                raise ValueError("Invalid preview token signature")
            payload = json.loads(self._base64url_decode(encoded_payload))
        except (binascii.Error, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid preview token") from exc

        now = now or datetime.now(timezone.utc)
        if not isinstance(payload, dict):
            raise ValueError("Invalid preview token payload")
        if payload.get("purpose") != "custom_ai_report_preview":
            raise ValueError("Invalid preview token purpose")
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= int(now.timestamp()):
            raise ValueError("Expired preview token")
        return payload

    def _encode_token(self, payload: dict) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        encoded_payload = self._base64url_encode(serialized)
        signature = hmac.new(self.token_secret, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded_payload}.{self._base64url_encode(signature)}"

    @staticmethod
    def summary_hash(summary: CustomClinicalSummary) -> str:
        serialized = json.dumps(
            summary.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _base64url_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _base64url_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
