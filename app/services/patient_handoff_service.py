from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.access_policy import AccessPolicy
from app.models.models import Anamnese, DailyReport, DietDocument, Supplement, User
from app.models.schemas import (
    CustomAiReportPeriod,
    DietDocumentRead,
    PatientHandoffAllergyMatch,
    PatientHandoffSummary,
    SupplementRead,
)
from app.services.allergy_correlation_service import AllergyCorrelationService
from app.services.anamnese_clinical_service import AnamneseClinicalService
from app.services.custom_report_service import CustomReportService
from app.services.daily_report_service import DailyReportService
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
            possible_allergy_matches=self._allergy_matches(anamnese, patient_id, resolved_start, resolved_end),
        )

    def _allergy_matches(
        self, anamnese: Anamnese | None, patient_id: int, start_date: date, end_date: date
    ) -> list[PatientHandoffAllergyMatch]:
        # Cheap to skip entirely when nothing is registered -- avoids querying
        # and decrypting DailyReports for the common case (no allergies on file).
        if not anamnese or not (anamnese.medication_allergies or anamnese.food_restrictions):
            return []

        reports = (
            self.db.query(DailyReport)
            .filter(
                DailyReport.user_id == patient_id,
                DailyReport.report_date >= start_date,
                DailyReport.report_date <= end_date,
                or_(
                    DailyReport.symptom_description.isnot(None),
                    DailyReport.symptom_description_encryption_envelope.isnot(None),
                    DailyReport.lifestyle_notes.isnot(None),
                    DailyReport.lifestyle_notes_encryption_envelope.isnot(None),
                ),
            )
            .order_by(DailyReport.report_date.asc())
            .all()
        )

        results: list[PatientHandoffAllergyMatch] = []
        for report in reports:
            DailyReportService.hydrate_clinical(report)
            matched_terms = AllergyCorrelationService.find_matches(
                anamnese,
                symptom_description=report.symptom_description,
                lifestyle_notes=report.lifestyle_notes,
            )
            if matched_terms:
                results.append(PatientHandoffAllergyMatch(report_date=report.report_date, matched_terms=matched_terms))
        return results

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
