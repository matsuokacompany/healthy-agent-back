from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.models import AiReportCache, Anamnese, DailyReport
from app.services.clinical_data_service import ClinicalDataService


class ClinicalEncryptionRotationError(RuntimeError):
    """A clinical envelope could not be safely rotated."""


@dataclass
class RotationStats:
    records: int = 0
    fields: int = 0


class ClinicalEncryptionRotationService:
    """Re-encrypt clinical envelopes with the configured active key version."""

    TARGETS = (
        (Anamnese, (("info", "text"),)),
        (DailyReport, (("symptom_description", "text"), ("suspected_cause", "text"))),
        (AiReportCache, (("clinical_summary", "text"), ("ai_response", "json"))),
    )

    def __init__(self, db: Session, clinical_data: ClinicalDataService | None = None):
        self.db = db
        self.clinical_data = clinical_data or ClinicalDataService(write_plaintext=False)

    def pending_counts(self, target_key_version: str) -> dict[str, int]:
        self._validate_target(target_key_version)
        counts = {}
        for model, fields in self.TARGETS:
            count = 0
            for record in self._records_with_envelopes(model, fields):
                if any(self._requires_rotation(record, name, target_key_version) for name, _ in fields):
                    count += 1
            counts[model.__tablename__] = count
        return counts

    def run(
        self,
        target_key_version: str,
        *,
        batch_size: int = 100,
        max_records: int | None = None,
    ) -> RotationStats:
        self._validate_target(target_key_version)
        if batch_size < 1 or (max_records is not None and max_records < 1):
            raise ValueError("batch_size and max_records must be at least 1")
        stats = RotationStats()
        for model, fields in self.TARGETS:
            last_id = 0
            while max_records is None or stats.records < max_records:
                limit = batch_size if max_records is None else min(batch_size, max_records - stats.records)
                query = self.db.query(model).filter(
                    model.id > last_id,
                    self._envelope_filter(model, fields),
                ).order_by(model.id).limit(limit)
                if self.db.get_bind().dialect.name == "postgresql":
                    query = query.with_for_update(skip_locked=True)
                records = query.all()
                if not records:
                    break
                for record in records:
                    last_id = record.id
                    rotated_record = False
                    for name, value_type in fields:
                        if not self._requires_rotation(record, name, target_key_version):
                            continue
                        value = self.clinical_data.read_json(record, name) if value_type == "json" else self.clinical_data.read_text(record, name)
                        if value_type == "json":
                            self.clinical_data.write_json(record, name, value)
                            verified = self.clinical_data.read_json(record, name)
                        else:
                            self.clinical_data.write_text(record, name, value)
                            verified = self.clinical_data.read_text(record, name)
                        if verified != value:
                            self.db.rollback()
                            raise ClinicalEncryptionRotationError(
                                f"Rotation verification failed: table={record.__tablename__} record_id={record.id} field={name}"
                            )
                        stats.fields += 1
                        rotated_record = True
                    if rotated_record:
                        stats.records += 1
                self.db.commit()
                self.db.expunge_all()
        return stats

    def _validate_target(self, target_key_version: str) -> None:
        if not target_key_version:
            raise ValueError("target_key_version is required")
        active = self.clinical_data.encryption.active_key_version
        if target_key_version != active:
            raise ClinicalEncryptionRotationError(
                f"Target key version {target_key_version!r} does not match active version {active!r}"
            )

    def _records_with_envelopes(self, model, fields):
        return self.db.query(model).filter(self._envelope_filter(model, fields)).all()

    @staticmethod
    def _envelope_filter(model, fields):
        return or_(*(getattr(model, f"{name}_encryption_envelope").is_not(None) for name, _ in fields))

    @staticmethod
    def _requires_rotation(record, name: str, target_key_version: str) -> bool:
        envelope = getattr(record, f"{name}_encryption_envelope")
        return envelope is not None and envelope.get("key_version") != target_key_version
