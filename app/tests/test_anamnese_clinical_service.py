from types import SimpleNamespace

from app.services.anamnese_clinical_service import AnamneseClinicalService


def test_anamnese_write_delegates_to_clinical_service(monkeypatch):
    class FakeClinicalDataService:
        def write_text(self, record, field, value):
            record.info = value
            record.info_encryption_envelope = {"encrypted": True}

    monkeypatch.setattr("app.services.anamnese_clinical_service.ClinicalDataService", FakeClinicalDataService)
    monkeypatch.setattr("app.services.anamnese_clinical_service.settings.CLINICAL_ENCRYPTION_PROVIDER", "aws_kms")
    record = SimpleNamespace(info=None, info_encryption_envelope=None)

    AnamneseClinicalService.write(record, "Histórico")

    assert record.info == "Histórico"
    assert record.info_encryption_envelope == {"encrypted": True}


def test_anamnese_hybrid_read_prefers_envelope(monkeypatch):
    class FakeClinicalDataService:
        def read_text(self, record, field):
            return "Envelope"

    monkeypatch.setattr("app.services.anamnese_clinical_service.ClinicalDataService", FakeClinicalDataService)
    monkeypatch.setattr(
        "app.services.anamnese_clinical_service.set_committed_value",
        lambda record, field, value: setattr(record, field, value),
    )
    record = SimpleNamespace(
        info="Plaintext",
        info_encryption_envelope={"encrypted": True},
        medication_allergies=None,
        medication_allergies_encryption_envelope=None,
        food_restrictions=None,
        food_restrictions_encryption_envelope=None,
    )

    AnamneseClinicalService.hydrate(record)

    assert record.info == "Envelope"


def test_anamnese_hydrate_also_decrypts_allergy_fields(monkeypatch):
    class FakeClinicalDataService:
        def read_text(self, record, field):
            return f"Envelope:{field}"

    monkeypatch.setattr("app.services.anamnese_clinical_service.ClinicalDataService", FakeClinicalDataService)
    monkeypatch.setattr(
        "app.services.anamnese_clinical_service.set_committed_value",
        lambda record, field, value: setattr(record, field, value),
    )
    record = SimpleNamespace(
        info="Plaintext",
        info_encryption_envelope=None,
        medication_allergies="Dipirona",
        medication_allergies_encryption_envelope={"encrypted": True},
        food_restrictions="Lactose",
        food_restrictions_encryption_envelope={"encrypted": True},
    )

    AnamneseClinicalService.hydrate(record)

    assert record.info == "Plaintext"
    assert record.medication_allergies == "Envelope:medication_allergies"
    assert record.food_restrictions == "Envelope:food_restrictions"


def test_anamnese_hydrate_skips_clinical_service_when_no_envelopes(monkeypatch):
    # Regression: hydrate() used to always construct ClinicalDataService()
    # regardless of whether any field actually had an envelope, which broke
    # (raised ClinicalEncryptionConfigurationError) for a freshly-created
    # record with CLINICAL_ENCRYPTION_PROVIDER not configured for aws_kms.
    def boom(*args, **kwargs):
        raise AssertionError("ClinicalDataService should not be constructed when nothing needs decrypting")

    monkeypatch.setattr("app.services.anamnese_clinical_service.ClinicalDataService", boom)
    record = SimpleNamespace(
        info="Plaintext",
        info_encryption_envelope=None,
        medication_allergies=None,
        medication_allergies_encryption_envelope=None,
        food_restrictions=None,
        food_restrictions_encryption_envelope=None,
    )

    AnamneseClinicalService.hydrate(record)

    assert record.info == "Plaintext"


def test_anamnese_initial_plaintext_is_null_after_cutover(monkeypatch):
    monkeypatch.setattr("app.services.anamnese_clinical_service.settings.CLINICAL_ENCRYPTION_PROVIDER", "aws_kms")
    monkeypatch.setattr(
        "app.services.anamnese_clinical_service.settings.CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED",
        False,
    )

    assert AnamneseClinicalService.initial_plaintext("Histórico") is None
