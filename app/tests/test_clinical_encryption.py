from dataclasses import replace

import pytest

from app.core.clinical_encryption import (
    AwsKmsDataKeyProvider,
    ClinicalEncryptionConfigurationError,
    ClinicalEncryptionError,
    ClinicalEncryptionService,
    LocalDataKeyProvider,
)


CONTEXT = {
    "table": "daily_reports",
    "record_id": "101",
    "patient_id": "7",
    "field": "symptom_description",
}


def _service() -> ClinicalEncryptionService:
    return ClinicalEncryptionService(LocalDataKeyProvider(b"k" * 32), active_key_version="v1")


def test_encrypts_and_decrypts_unicode_clinical_text():
    service = _service()
    encrypted = service.encrypt("Febre, náusea e dor de cabeça.", context=CONTEXT)

    assert service.decrypt(encrypted, context=CONTEXT) == "Febre, náusea e dor de cabeça."
    assert b"Febre" not in encrypted.ciphertext
    assert encrypted.algorithm == "AES-256-GCM"
    assert encrypted.envelope_version == 1
    assert encrypted.key_version == "v1"


def test_same_value_uses_distinct_ciphertexts_and_data_keys():
    service = _service()

    first = service.encrypt("febre", context=CONTEXT)
    second = service.encrypt("febre", context=CONTEXT)

    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext
    assert first.encrypted_data_key != second.encrypted_data_key


@pytest.mark.parametrize("attribute", ["ciphertext", "nonce", "encrypted_data_key"])
def test_rejects_tampered_envelope(attribute):
    service = _service()
    encrypted = service.encrypt("febre", context=CONTEXT)
    original = getattr(encrypted, attribute)
    tampered = replace(encrypted, **{attribute: original[:-1] + bytes([original[-1] ^ 1])})

    with pytest.raises(ClinicalEncryptionError):
        service.decrypt(tampered, context=CONTEXT)


@pytest.mark.parametrize(
    ("context_key", "new_value"),
    [("patient_id", "8"), ("record_id", "102"), ("field", "suspected_cause"), ("table", "anamneses")],
)
def test_rejects_context_from_another_patient_record_or_field(context_key, new_value):
    service = _service()
    encrypted = service.encrypt("febre", context=CONTEXT)
    wrong_context = {**CONTEXT, context_key: new_value}

    with pytest.raises(ClinicalEncryptionError):
        service.decrypt(encrypted, context=wrong_context)


def test_requires_complete_context():
    with pytest.raises(ClinicalEncryptionConfigurationError):
        _service().encrypt("febre", context={"patient_id": "7"})


def test_forbids_local_provider_in_production():
    with pytest.raises(ClinicalEncryptionConfigurationError):
        LocalDataKeyProvider(b"k" * 32, environment="production")


class FakeKmsClient:
    def __init__(self):
        self.key = b"d" * 32
        self.encryption_context = None

    def generate_data_key(self, **kwargs):
        self.encryption_context = kwargs["EncryptionContext"]
        return {"Plaintext": self.key, "CiphertextBlob": b"wrapped-key", "KeyId": "kms-key-arn"}

    def decrypt(self, **kwargs):
        assert kwargs["CiphertextBlob"] == b"wrapped-key"
        assert kwargs["KeyId"] == "kms-key-arn"
        assert kwargs["EncryptionContext"] == self.encryption_context
        return {"Plaintext": self.key}


def test_aws_kms_provider_binds_data_key_to_encryption_context():
    client = FakeKmsClient()
    service = ClinicalEncryptionService(
        AwsKmsDataKeyProvider("configured-key", "sa-east-1", kms_client=client),
        active_key_version="v1",
    )

    encrypted = service.encrypt("febre", context=CONTEXT)

    assert service.decrypt(encrypted, context=CONTEXT) == "febre"
    assert client.encryption_context == CONTEXT
