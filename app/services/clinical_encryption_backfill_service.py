from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.models import AiReportCache, Anamnese, DailyReport
from app.services.clinical_data_service import ClinicalDataService


@dataclass
class BackfillStats:
    records: int = 0
    fields: int = 0


class ClinicalEncryptionBackfillService:
    """Restartable, batched backfill for legacy clinical plaintext values."""

    TARGETS = (
        (Anamnese, ("info",)),
        (DailyReport, ("symptom_description", "suspected_cause")),
        (AiReportCache, ("clinical_summary", "ai_response")),
    )

    def __init__(self, db: Session, clinical_data: ClinicalDataService | None = None):
        self.db = db
        self.clinical_data = clinical_data

    def pending_counts(self) -> dict[str, int]:
        return {
            model.__tablename__: self.db.query(model).filter(self._pending_filter(model, fields)).count()
            for model, fields in self.TARGETS
        }

    def run(self, *, batch_size: int = 100, max_records: int | None = None) -> BackfillStats:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be at least 1")
        if self.clinical_data is None:
            self.clinical_data = ClinicalDataService()

        stats = BackfillStats()
        for model, fields in self.TARGETS:
            last_id = 0
            while max_records is None or stats.records < max_records:
                limit = batch_size if max_records is None else min(batch_size, max_records - stats.records)
                query = (
                    self.db.query(model)
                    .filter(model.id > last_id, self._pending_filter(model, fields))
                    .order_by(model.id)
                    .limit(limit)
                )
                if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
                    query = query.with_for_update(skip_locked=True)
                records = query.all()
                if not records:
                    break

                for record in records:
                    last_id = record.id
                    for field in fields:
                        value = getattr(record, field)
                        envelope = getattr(record, f"{field}_encryption_envelope")
                        if value is not None and envelope is None:
                            if isinstance(value, str):
                                self.clinical_data.write_text(record, field, value)
                            else:
                                self.clinical_data.write_json(record, field, value)
                            stats.fields += 1
                    stats.records += 1
                self.db.commit()
                self.db.expunge_all()
        return stats

    @staticmethod
    def _pending_filter(model: Any, fields: tuple[str, ...]):
        return or_(
            *(and_(getattr(model, field).is_not(None), getattr(model, f"{field}_encryption_envelope").is_(None)) for field in fields)
        )
