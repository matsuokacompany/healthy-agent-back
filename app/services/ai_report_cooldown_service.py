import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import AiReportCache, AiReportStatusEnum, User
from app.models.schemas import AiReportCooldownReleaseResponse


logger = logging.getLogger(__name__)


class AiReportCooldownService:
    def __init__(self, db: Session):
        self.db = db

    def release_once(
        self,
        *,
        patient_id: int,
        mode: str,
        released_by: User,
        now: datetime | None = None,
    ) -> AiReportCooldownReleaseResponse:
        patient = self.db.query(User).filter(User.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        active_report = (
            self.db.query(AiReportCache)
            .filter(
                AiReportCache.patient_id == patient_id,
                AiReportCache.status.in_([AiReportStatusEnum.PENDING.value, AiReportStatusEnum.PROCESSING.value]),
            )
            .first()
        )
        if active_report:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI report already in progress")

        report = (
            self.db.query(AiReportCache)
            .filter(
                AiReportCache.patient_id == patient_id,
                AiReportCache.modo == mode,
                AiReportCache.status == AiReportStatusEnum.COMPLETED.value,
                AiReportCache.generated_at.is_not(None),
            )
            .order_by(AiReportCache.generated_at.desc(), AiReportCache.id.desc())
            .first()
        )
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Completed AI report not found for this patient and mode",
            )

        released_at = now or datetime.now(timezone.utc)
        previous_next_generation_at = report.next_generation_at
        if not previous_next_generation_at or self._as_utc(previous_next_generation_at) <= self._as_utc(released_at):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI report cooldown is not active")

        report.next_generation_at = released_at
        logger.warning(
            "Super admin released AI report cooldown patient_id=%s report_id=%s mode=%s "
            "released_by_user_id=%s previous_next_generation_at=%s released_at=%s",
            patient_id,
            report.id,
            mode,
            released_by.id,
            previous_next_generation_at,
            released_at,
        )
        self.db.commit()
        return AiReportCooldownReleaseResponse(
            patient_id=patient_id,
            report_id=report.id,
            modo=mode,
            released_by_user_id=released_by.id,
            previous_next_generation_at=previous_next_generation_at,
            released_at=released_at,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
