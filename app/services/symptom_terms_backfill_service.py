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
    over completed, symptomatic check-ins. By default only touches check-ins
    with no linked term yet (predating the symptom_terms vocabulary from
    alembic 0028, or missed by an earlier classifier run) — the gap that
    made CustomReportService fall back to raw free text instead of a
    normalized term. Pass reclassify_all=True to instead re-run every
    completed, symptomatic check-in against the current prompt, e.g. after
    a prompt fix that changes what already-classified reports should have
    produced.
    """

    def __init__(self, db: Session):
        self.db = db

    def pending_count(self, *, reclassify_all: bool = False) -> int:
        return self._pending_query(reclassify_all=reclassify_all).count()

    def run(
        self,
        *,
        batch_size: int = 100,
        max_records: int | None = None,
        reclassify_all: bool = False,
    ) -> SymptomTermsBackfillStats:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be at least 1")

        stats = SymptomTermsBackfillStats()
        last_id = 0
        while max_records is None or stats.processed < max_records:
            limit = batch_size if max_records is None else min(batch_size, max_records - stats.processed)
            reports = (
                self._pending_query(reclassify_all=reclassify_all)
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
                # normalize() replaces a report's prior links (delete-then-insert),
                # so reprocessing an already-classified report is safe/idempotent —
                # that's what lets reclassify_all re-run everything against an
                # improved prompt instead of only ever touching untouched reports.
                SymptomNormalizationService.normalize(self.db, report, symptom_description)
                stats.processed += 1
                if self._is_linked(report.id):
                    stats.linked += 1

        return stats

    def _pending_query(self, *, reclassify_all: bool = False):
        query = self.db.query(DailyReport).filter(
            DailyReport.completed.is_(True), DailyReport.had_symptoms.is_(True)
        )
        if reclassify_all:
            return query
        linked = (
            self.db.query(DailyReportSymptomTerm.daily_report_id)
            .filter(DailyReportSymptomTerm.daily_report_id == DailyReport.id)
            .exists()
        )
        return query.filter(~linked)

    def _is_linked(self, report_id: int) -> bool:
        return (
            self.db.query(DailyReportSymptomTerm.daily_report_id)
            .filter(DailyReportSymptomTerm.daily_report_id == report_id)
            .first()
            is not None
        )
