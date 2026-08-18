from dataclasses import dataclass, field

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.models import AiReportCache, Anamnese, DailyReport
from app.services.clinical_data_service import ClinicalDataService


@dataclass(frozen=True)
class VerificationIssue:
    table: str
    record_id: int
    field: str
    kind: str


@dataclass
class VerificationResult:
    records: int = 0
    fields: int = 0
    mismatches: int = 0
    failures: int = 0
    issues: list[VerificationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.mismatches == 0 and self.failures == 0


class ClinicalEncryptionVerificationService:
    """Read-only verification of stored clinical envelopes against dual-written values."""

    TARGETS = (
        (Anamnese, (("info", "text"),)),
        (DailyReport, (("symptom_description", "text"), ("suspected_cause", "text"))),
        (AiReportCache, (("clinical_summary", "text"), ("ai_response", "json"))),
    )

    def __init__(self, db: Session, clinical_data: ClinicalDataService | None = None):
        self.db = db
        self.clinical_data = clinical_data or ClinicalDataService()

    def run(self, *, batch_size: int = 100, max_records: int | None = None) -> VerificationResult:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be at least 1")

        result = VerificationResult()
        for model, fields in self.TARGETS:
            last_id = 0
            while max_records is None or result.records < max_records:
                limit = batch_size if max_records is None else min(batch_size, max_records - result.records)
                records = (
                    self.db.query(model)
                    .filter(
                        model.id > last_id,
                        or_(*(getattr(model, f"{name}_encryption_envelope").is_not(None) for name, _ in fields)),
                    )
                    .order_by(model.id)
                    .limit(limit)
                    .all()
                )
                if not records:
                    break

                for record in records:
                    last_id = record.id
                    result.records += 1
                    for name, value_type in fields:
                        if getattr(record, f"{name}_encryption_envelope") is None:
                            continue
                        result.fields += 1
                        try:
                            decrypted = (
                                self.clinical_data.read_json(record, name)
                                if value_type == "json"
                                else self.clinical_data.read_text(record, name)
                            )
                        except Exception:
                            result.failures += 1
                            result.issues.append(self._issue(record, name, "decrypt_failure"))
                            continue
                        plaintext = getattr(record, name)
                        if plaintext is not None and decrypted != plaintext:
                            result.mismatches += 1
                            result.issues.append(self._issue(record, name, "plaintext_mismatch"))
                self.db.expunge_all()
        return result

    @staticmethod
    def _issue(record, field_name: str, kind: str) -> VerificationIssue:
        return VerificationIssue(
            table=record.__tablename__,
            record_id=record.id,
            field=field_name,
            kind=kind,
        )
