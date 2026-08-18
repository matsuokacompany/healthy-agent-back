from types import SimpleNamespace

import pytest

from app.models.models import Anamnese
from app.services.clinical_encryption_verification_service import ClinicalEncryptionVerificationService


class FakeQuery:
    def __init__(self, records):
        self.records = records
        self.last_id = 0
        self.limit_value = None

    def filter(self, id_filter, _envelope_filter):
        self.last_id = id_filter.right.value
        return self

    def order_by(self, _column):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return [record for record in self.records if record.id > self.last_id][: self.limit_value]


class FakeSession:
    def __init__(self, records_by_model):
        self.records_by_model = records_by_model

    def query(self, model):
        return FakeQuery(self.records_by_model.get(model, []))

    def expunge_all(self):
        pass


class FakeClinicalData:
    def read_text(self, record, field):
        value = getattr(record, f"decrypted_{field}")
        if isinstance(value, Exception):
            raise value
        return value

    def read_json(self, record, field):
        return self.read_text(record, field)


def _record(record_id, plaintext, decrypted, envelope=True):
    return SimpleNamespace(
        id=record_id,
        __tablename__="anamneses",
        info=plaintext,
        decrypted_info=decrypted,
        info_encryption_envelope={"ciphertext": "redacted"} if envelope else None,
    )


def _service(records):
    service = ClinicalEncryptionVerificationService(FakeSession({Anamnese: records}), FakeClinicalData())
    service.TARGETS = ((Anamnese, (("info", "text"),)),)
    return service


def test_verifies_matches_without_exposing_values():
    result = _service([_record(1, "clinical plaintext", "clinical plaintext")]).run()

    assert result.valid
    assert (result.records, result.fields, result.mismatches, result.failures) == (1, 1, 0, 0)
    assert result.issues == []


def test_ciphertext_only_record_is_valid_when_decryption_succeeds():
    result = _service([_record(1, None, "clinical value")]).run()

    assert result.valid
    assert (result.records, result.fields, result.mismatches, result.failures) == (1, 1, 0, 0)


def test_reports_mismatch_and_decryption_failure_using_metadata_only():
    result = _service(
        [
            _record(1, "first secret", "different secret"),
            _record(2, "second secret", RuntimeError("KMS failed")),
        ]
    ).run(batch_size=1)

    assert not result.valid
    assert (result.mismatches, result.failures) == (1, 1)
    assert [(issue.record_id, issue.kind) for issue in result.issues] == [
        (1, "plaintext_mismatch"),
        (2, "decrypt_failure"),
    ]
    assert "secret" not in repr(result.issues)


@pytest.mark.parametrize("kwargs", [{"batch_size": 0}, {"max_records": 0}])
def test_rejects_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        _service([]).run(**kwargs)
