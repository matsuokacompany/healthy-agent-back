from types import SimpleNamespace

from app.scripts import symptom_terms_backfill


class FakeSessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, _exc_type, _exc, _traceback):
        return False


def test_dry_run_sets_service_context_and_does_not_call_run(monkeypatch):
    db = object()
    events = []

    monkeypatch.setattr(symptom_terms_backfill, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(
        symptom_terms_backfill, "set_database_service_context", lambda actual, name: events.append((actual, name))
    )
    monkeypatch.setattr(
        symptom_terms_backfill,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(execute=False, batch_size=100, max_records=None)),
    )

    def build_service(actual_db):
        assert events == [(db, "symptom_terms_backfill")]
        assert actual_db is db
        return SimpleNamespace(
            pending_count=lambda: 3,
            run=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("run() must not be called on a dry run")),
        )

    monkeypatch.setattr(symptom_terms_backfill, "SymptomTermsBackfillService", build_service)

    symptom_terms_backfill.main()


def test_execute_runs_backfill_after_setting_service_context(monkeypatch):
    db = object()
    events = []
    run_calls = []

    monkeypatch.setattr(symptom_terms_backfill, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(
        symptom_terms_backfill, "set_database_service_context", lambda actual, name: events.append((actual, name))
    )
    monkeypatch.setattr(
        symptom_terms_backfill,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(execute=True, batch_size=50, max_records=10)),
    )

    pending_calls = [3, 1]

    def build_service(actual_db):
        assert events == [(db, "symptom_terms_backfill")]
        assert actual_db is db
        return SimpleNamespace(
            pending_count=lambda: pending_calls.pop(0),
            run=lambda **kwargs: run_calls.append(kwargs) or SimpleNamespace(processed=2, linked=1),
        )

    monkeypatch.setattr(symptom_terms_backfill, "SymptomTermsBackfillService", build_service)

    symptom_terms_backfill.main()

    assert run_calls == [{"batch_size": 50, "max_records": 10}]
