from dataclasses import dataclass

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.models import AiReportCache, Anamnese, DailyReport
from app.services.clinical_data_service import ClinicalDataService


class ClinicalPlaintextCleanupError(RuntimeError):
    """A plaintext value could not be safely matched to its envelope."""


@dataclass
class CleanupStats:
    records: int = 0
    fields: int = 0


class ClinicalPlaintextCleanupService:
    """Clear dual-written plaintext only after authenticating an equal envelope."""

    TARGETS = (
        (Anamnese, (("info", "text"),)),
        (DailyReport, (("symptom_description", "text"), ("suspected_cause", "text"))),
        (AiReportCache, (("clinical_summary", "text"), ("ai_response", "json"))),
    )

    def __init__(self, db: Session, clinical_data: ClinicalDataService | None = None):
        self.db = db
        self.clinical_data = clinical_data or ClinicalDataService()

    def pending_counts(self) -> dict[str, int]:
        return {
            model.__tablename__: self.db.query(model).filter(self._pending_filter(model, fields)).count()
            for model, fields in self.TARGETS
        }

    def run(self, *, batch_size: int = 100, max_records: int | None = None) -> CleanupStats:
        if batch_size < 1 or (max_records is not None and max_records < 1):
            raise ValueError("batch_size and max_records must be at least 1")
        stats = CleanupStats()
        for model, fields in self.TARGETS:
            last_id = 0
            while max_records is None or stats.records < max_records:
                limit = batch_size if max_records is None else min(batch_size, max_records - stats.records)
                query = self.db.query(model).filter(
                    model.id > last_id, self._pending_filter(model, fields)
                ).order_by(model.id).limit(limit)
                if self.db.get_bind().dialect.name == "postgresql":
                    query = query.with_for_update(skip_locked=True)
                records = query.all()
                if not records:
                    break
                for record in records:
                    last_id = record.id
                    for name, value_type in fields:
                        plaintext = getattr(record, name)
                        if plaintext is None or getattr(record, f"{name}_encryption_envelope") is None:
                            continue
                        decrypted = self.clinical_data.read_json(record, name) if value_type == "json" else self.clinical_data.read_text(record, name)
                        if decrypted != plaintext:
                            self.db.rollback()
                            raise ClinicalPlaintextCleanupError(
                                f"Envelope mismatch: table={record.__tablename__} record_id={record.id} field={name}"
                            )
                        setattr(record, name, None)
                        stats.fields += 1
                    stats.records += 1
                self.db.commit()
                self.db.expunge_all()
        return stats

    @staticmethod
    def _pending_filter(model, fields):
        return or_(*(and_(getattr(model, name).is_not(None), getattr(model, f"{name}_encryption_envelope").is_not(None)) for name, _ in fields))
