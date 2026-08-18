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
    record = SimpleNamespace(info="Plaintext", info_encryption_envelope={"encrypted": True})

    AnamneseClinicalService.hydrate(record)

    assert record.info == "Envelope"
