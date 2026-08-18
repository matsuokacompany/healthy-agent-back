import json
from typing import Any

from app.core.clinical_encryption import (
    ClinicalCiphertext,
    ClinicalEncryptionConfigurationError,
    ClinicalEncryptionService,
    build_clinical_encryption_service,
)
from app.core.config import settings


class ClinicalDataService:
    """Dual-write and hybrid-read helpers for persisted clinical fields."""

    def __init__(
        self,
        encryption: ClinicalEncryptionService | None = None,
        *,
        write_plaintext: bool | None = None,
    ):
        self.encryption = encryption or build_clinical_encryption_service(settings)
        self.write_plaintext = (
            settings.CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED
            if write_plaintext is None
            else write_plaintext
        )

    def write_text(self, record: Any, field: str, value: str | None) -> None:
        self._require_identity(record)
        envelope_field = f"{field}_encryption_envelope"
        if value is None:
            setattr(record, field, None)
            setattr(record, envelope_field, None)
            return
        encrypted = self.encryption.encrypt(value, context=self._context(record, field))
        setattr(record, field, value if self.write_plaintext else None)
        setattr(record, envelope_field, encrypted.to_storage_dict())

    def read_text(self, record: Any, field: str) -> str | None:
        envelope = getattr(record, f"{field}_encryption_envelope")
        if envelope is None:
            return getattr(record, field)
        encrypted = ClinicalCiphertext.from_storage_dict(envelope)
        return self.encryption.decrypt(encrypted, context=self._context(record, field))

    def write_json(self, record: Any, field: str, value: Any | None) -> None:
        serialized = None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.write_text(record, field, serialized)
        setattr(record, field, value if self.write_plaintext else None)

    def read_json(self, record: Any, field: str) -> Any | None:
        envelope = getattr(record, f"{field}_encryption_envelope")
        if envelope is None:
            return getattr(record, field)
        return json.loads(self.read_text(record, field))

    @staticmethod
    def _require_identity(record: Any) -> None:
        if getattr(record, "id", None) is None:
            raise ClinicalEncryptionConfigurationError("Clinical records must be flushed before encryption")

    @staticmethod
    def _context(record: Any, field: str) -> dict[str, str]:
        patient_id = getattr(record, "patient_id", None) or getattr(record, "user_id", None)
        if patient_id is None:
            raise ClinicalEncryptionConfigurationError("Clinical records require a patient identity")
        return {
            "table": record.__tablename__,
            "record_id": str(record.id),
            "patient_id": str(patient_id),
            "field": field,
        }
