from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.access_policy import AccessPolicy
from app.models.models import Anamnese, DietDocument, Supplement, User
from app.models.schemas import CustomAiReportPeriod, DietDocumentRead, PatientHandoffSummary, SupplementRead
from app.services.anamnese_clinical_service import AnamneseClinicalService
from app.services.custom_report_service import CustomReportService
from app.services.red_flag_symptoms import ANAMNESE_RISK_FACTOR_FIELDS, ANAMNESE_RISK_FACTOR_LABELS

DEFAULT_PERIOD_DAYS = 90


class PatientHandoffService:
    """Assembles a deterministic, non-AI clinical summary meant to be
    printed/downloaded and handed to a health professional -- see
    PatientHandoffSummary's docstring. Uses AccessPolicy.require_patient_read
    the same way ClinicalAttachmentService does, so it works both for a
    self-monitoring patient pulling their own data and for a professional
    linked to that patient."""

    def __init__(self, db: Session):
        self.db = db

    def get_summary(
        self,
        actor: User,
        patient_id: int,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PatientHandoffSummary:
        AccessPolicy(self.db, actor).require_patient_read(patient_id)
        resolved_start, resolved_end = self._resolve_period(start_date, end_date)

        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if anamnese:
            AnamneseClinicalService.hydrate(anamnese)

        supplements = (
            self.db.query(Supplement)
            .filter(Supplement.patient_id == patient_id)
            .order_by(Supplement.name.asc())
            .all()
        )
        diet_document = self.db.query(DietDocument).filter(DietDocument.patient_id == patient_id).first()
        monitoring_summary = CustomReportService(self.db).build_summary(patient_id, resolved_start, resolved_end)

        return PatientHandoffSummary(
            patient_id=patient_id,
            generated_at=datetime.now(timezone.utc),
            anamnese_info=anamnese.info if anamnese else None,
            risk_factors=self._risk_factor_labels(anamnese),
            medication_allergies=anamnese.medication_allergies if anamnese else None,
            food_restrictions=anamnese.food_restrictions if anamnese else None,
            supplements=[SupplementRead.model_validate(supplement) for supplement in supplements],
            diet_document=DietDocumentRead.model_validate(diet_document) if diet_document else None,
            monitoring_summary=monitoring_summary,
        )

    @staticmethod
    def _risk_factor_labels(anamnese: Anamnese | None) -> list[str]:
        if not anamnese:
            return []
        return [
            ANAMNESE_RISK_FACTOR_LABELS[field]
            for field in ANAMNESE_RISK_FACTOR_FIELDS
            if getattr(anamnese, field) is True
        ]

    @staticmethod
    def _resolve_period(start_date: date | None, end_date: date | None) -> tuple[date, date]:
        today = datetime.now(timezone.utc).date()
        resolved_end = end_date or today
        resolved_start = start_date or (resolved_end - timedelta(days=DEFAULT_PERIOD_DAYS - 1))
        # CustomReportService.build_summary validates the period through the
        # same CustomAiReportPeriod the professional custom-AI-report flow
        # uses (30-day minimum, 5-year maximum) -- surface a clean 422 here
        # instead of letting that ValidationError leak out as an unhandled 500.
        try:
            CustomAiReportPeriod(start_date=resolved_start, end_date=resolved_end)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return resolved_start, resolved_end
