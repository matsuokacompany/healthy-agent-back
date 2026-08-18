from types import SimpleNamespace

import pytest

from app.core.clinical_encryption import (
    ClinicalEncryptionConfigurationError,
    ClinicalEncryptionService,
    LocalDataKeyProvider,
)
from app.services.clinical_data_service import ClinicalDataService


def _service():
    encryption = ClinicalEncryptionService(LocalDataKeyProvider(b"k" * 32), active_key_version="v1")
    return ClinicalDataService(encryption)


def _record(**values):
    defaults = {
        "__tablename__": "daily_reports",
        "id": 10,
        "user_id": 7,
        "symptom_description": None,
        "symptom_description_encryption_envelope": None,
        "ai_response": None,
        "ai_response_encryption_envelope": None,
    }
    return SimpleNamespace(**{**defaults, **values})


def test_dual_write_and_hybrid_read_text():
    record = _record()
    service = _service()
    service.write_text(record, "symptom_description", "Febre")
    assert record.symptom_description == "Febre"
    assert service.read_text(record, "symptom_description") == "Febre"
    assert "Febre" not in str(record.symptom_description_encryption_envelope)


def test_hybrid_read_falls_back_to_legacy_plaintext():
    assert _service().read_text(_record(symptom_description="Legado"), "symptom_description") == "Legado"


def test_json_round_trip():
    record = _record()
    service = _service()
    service.write_json(record, "ai_response", {"resultado": "estável"})
    assert service.read_json(record, "ai_response") == {"resultado": "estável"}


def test_rejects_unflushed_record():
    with pytest.raises(ClinicalEncryptionConfigurationError):
        _service().write_text(_record(id=None), "symptom_description", "Febre")
