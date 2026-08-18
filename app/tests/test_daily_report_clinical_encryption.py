from types import SimpleNamespace

from app.services.daily_report_service import DailyReportService


def test_daily_report_clinical_write_uses_encryption_service(monkeypatch):
    writes = []

    class FakeClinicalDataService:
        def write_text(self, report, field, value):
            writes.append((field, value))
            setattr(report, field, value)
            setattr(report, f"{field}_encryption_envelope", {"encrypted": True} if value else None)

    monkeypatch.setattr("app.services.daily_report_service.ClinicalDataService", FakeClinicalDataService)
    monkeypatch.setattr("app.services.daily_report_service.settings.CLINICAL_ENCRYPTION_PROVIDER", "aws_kms")
    report = SimpleNamespace(
        symptom_description=None,
        symptom_description_encryption_envelope=None,
        suspected_cause=None,
        suspected_cause_encryption_envelope=None,
    )

    DailyReportService._write_clinical(
        report,
        symptom_description="Febre",
        suspected_cause="Exposição",
    )

    assert writes == [("symptom_description", "Febre"), ("suspected_cause", "Exposição")]
    assert report.symptom_description_encryption_envelope == {"encrypted": True}
    assert report.suspected_cause_encryption_envelope == {"encrypted": True}


def test_daily_report_clinical_clear_removes_both_envelopes(monkeypatch):
    monkeypatch.setattr("app.services.daily_report_service.settings.CLINICAL_ENCRYPTION_PROVIDER", "disabled")
    monkeypatch.setattr("app.services.daily_report_service.settings.ENV", "test")
    report = SimpleNamespace(
        symptom_description="Febre",
        symptom_description_encryption_envelope={"encrypted": True},
        suspected_cause="Exposição",
        suspected_cause_encryption_envelope={"encrypted": True},
    )

    DailyReportService._write_clinical(report, symptom_description=None, suspected_cause=None)

    assert report.symptom_description is None
    assert report.symptom_description_encryption_envelope is None
    assert report.suspected_cause is None
    assert report.suspected_cause_encryption_envelope is None


def test_hybrid_read_prefers_envelope_without_marking_plaintext_dirty(monkeypatch):
    class FakeClinicalDataService:
        def read_text(self, report, field):
            return {"symptom_description": "Envelope", "suspected_cause": "Envelope cause"}[field]

    report = SimpleNamespace(
        symptom_description="Plaintext",
        symptom_description_encryption_envelope={"encrypted": True},
        suspected_cause="Plaintext cause",
        suspected_cause_encryption_envelope={"encrypted": True},
    )
    # SimpleNamespace is sufficient for the service contract, but SQLAlchemy's
    # committed-value helper is patched to assert the values selected for output.
    monkeypatch.setattr(
        "app.services.daily_report_service.set_committed_value",
        lambda target, field, value: setattr(target, field, value),
    )

    DailyReportService.hydrate_clinical(report, FakeClinicalDataService())

    assert report.symptom_description == "Envelope"
    assert report.suspected_cause == "Envelope cause"
