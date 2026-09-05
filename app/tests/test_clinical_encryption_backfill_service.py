import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.clinical_encryption import ClinicalEncryptionService, LocalDataKeyProvider
from app.models.models import AiReportCache, Anamnese, DailyReport
from app.services.clinical_data_service import ClinicalDataService
from app.services.clinical_encryption_backfill_service import ClinicalEncryptionBackfillService


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Anamnese.__table__.create(engine)
    DailyReport.__table__.create(engine)
    AiReportCache.__table__.create(engine)
    with Session(engine) as session:
        yield session


def _service(db):
    encryption = ClinicalEncryptionService(LocalDataKeyProvider(b"k" * 32), active_key_version="v1")
    return ClinicalEncryptionBackfillService(db, ClinicalDataService(encryption))


def test_backfills_text_and_json_fields_and_is_restartable(db):
    anamnese = Anamnese(user_id=7, info="Histórico")
    cached = AiReportCache(
        patient_id=7,
        professional_user_id=8,
        periodo="7d",
        modo="summary",
        status="COMPLETED",
        clinical_summary="Resumo",
        ai_response={"response_text": "Orientação clínica", "score": 2},
    )
    db.add_all((anamnese, cached))
    db.commit()

    service = _service(db)
    assert service.pending_counts() == {"anamneses": 1, "daily_reports": 0, "ai_report_cache": 1}
    stats = service.run(batch_size=1)

    assert (stats.records, stats.fields) == (2, 3)
    assert service.pending_counts() == {"anamneses": 0, "daily_reports": 0, "ai_report_cache": 0}
    # run() expunges everything from the session at the end of each batch
    # (intentional -- keeps a large production backfill's memory bounded), so
    # the objects added above are now detached; re-fetch them instead of
    # reusing those stale references.
    anamnese = db.query(Anamnese).filter_by(user_id=7).one()
    cached = db.query(AiReportCache).filter_by(patient_id=7).one()
    assert service.clinical_data.read_text(anamnese, "info") == "Histórico"
    assert service.clinical_data.read_json(cached, "ai_response") == {
        "response_text": "Orientação clínica",
        "score": 2,
    }
    assert service.run().records == 0


def test_preserves_existing_envelope_and_honors_record_limit(db):
    first = Anamnese(user_id=1, info="first", info_encryption_envelope={"already": "encrypted"})
    second = Anamnese(user_id=2, info="second")
    third = Anamnese(user_id=3, info="third")
    db.add_all((first, second, third))
    db.commit()

    stats = _service(db).run(max_records=1)

    assert (stats.records, stats.fields) == (1, 1)
    # run() expunges everything from the session once it's done (see above) --
    # re-fetch instead of reusing the now-detached references.
    first, second, third = (db.query(Anamnese).filter_by(user_id=user_id).one() for user_id in (1, 2, 3))
    assert first.info_encryption_envelope == {"already": "encrypted"}
    assert second.info_encryption_envelope is not None
    assert third.info_encryption_envelope is None


@pytest.mark.parametrize("kwargs", [{"batch_size": 0}, {"max_records": 0}])
def test_rejects_invalid_limits(db, kwargs):
    with pytest.raises(ValueError):
        _service(db).run(**kwargs)
