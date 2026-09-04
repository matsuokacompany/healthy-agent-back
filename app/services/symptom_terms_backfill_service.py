from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.models import DailyReport, DailyReportSymptomTerm
from app.services.daily_report_service import DailyReportService
from app.services.symptom_normalization_service import SymptomNormalizationService


@dataclass
class SymptomTermsBackfillStats:
    processed: int = 0
    linked: int = 0


class SymptomTermsBackfillService:
    """Restartable, batched backfill that runs SymptomNormalizationService
    over completed, symptomatic check-ins that predate the symptom_terms
    vocabulary (alembic 0028) and so were never classified — the same gap
    that made CustomReportService fall back to showing raw free text for
    old check-ins instead of a normalized term.
    """

    def __init__(self, db: Session):
        self.db = db

    def pending_count(self) -> int:
        return self._pending_query().count()

    def run(self, *, batch_size: int = 100, max_records: int | None = None) -> SymptomTermsBackfillStats:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be at least 1")

        stats = SymptomTermsBackfillStats()
        last_id = 0
        while max_records is None or stats.processed < max_records:
            limit = batch_size if max_records is None else min(batch_size, max_records - stats.processed)
            reports = (
                self._pending_query()
                .filter(DailyReport.id > last_id)
                .order_by(DailyReport.id.asc())
                .limit(limit)
                .all()
            )
            if not reports:
                break

            for report in reports:
                last_id = report.id
                symptom_description = DailyReportService.hydrate_clinical(report).symptom_description
                SymptomNormalizationService.normalize(self.db, report, symptom_description)
                stats.processed += 1
                if self._is_linked(report.id):
                    stats.linked += 1

        return stats

    def _pending_query(self):
        linked = (
            self.db.query(DailyReportSymptomTerm.daily_report_id)
            .filter(DailyReportSymptomTerm.daily_report_id == DailyReport.id)
            .exists()
        )
        return (
            self.db.query(DailyReport)
            .filter(DailyReport.completed.is_(True))
            .filter(DailyReport.had_symptoms.is_(True))
            .filter(~linked)
        )

    def _is_linked(self, report_id: int) -> bool:
        return (
            self.db.query(DailyReportSymptomTerm.daily_report_id)
            .filter(DailyReportSymptomTerm.daily_report_id == report_id)
            .first()
            is not None
        )
