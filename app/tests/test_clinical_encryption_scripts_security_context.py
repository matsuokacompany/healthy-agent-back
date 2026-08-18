from types import SimpleNamespace

import pytest

from app.scripts import clinical_encryption_backfill, clinical_encryption_verify


class FakeSessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, _exc_type, _exc, _traceback):
        return False


@pytest.mark.parametrize(
    ("module", "service_name", "result"),
    [
        (
            clinical_encryption_backfill,
            "clinical_encryption_backfill",
            SimpleNamespace(pending_counts=lambda: {"anamneses": 0}),
        ),
        (
            clinical_encryption_verify,
            "clinical_encryption_verification",
            SimpleNamespace(
                run=lambda **_kwargs: SimpleNamespace(
                    issues=[], records=0, fields=0, mismatches=0, failures=0, valid=True
                )
            ),
        ),
    ],
)
def test_maintenance_script_sets_service_context_before_querying(monkeypatch, module, service_name, result):
    db = object()
    events = []

    monkeypatch.setattr(module, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(module, "set_database_service_context", lambda actual, name: events.append((actual, name)))
    monkeypatch.setattr(module, "_parser", lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(
        execute=False, batch_size=100, max_records=None
    )))

    service_class_name = (
        "ClinicalEncryptionBackfillService"
        if module is clinical_encryption_backfill
        else "ClinicalEncryptionVerificationService"
    )

    def build_service(actual_db):
        assert events == [(db, service_name)]
        assert actual_db is db
        return result

    monkeypatch.setattr(module, service_class_name, build_service)

    module.main()
