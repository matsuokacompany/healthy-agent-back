from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MonitoringPlan,
    SymptomTerm,
    User,
)
from app.services.symptom_term_dedup_service import DuplicateCluster, SymptomTermDedupService

# Hand-picked so cosine similarity is predictable: "Náusea" is a near
# duplicate of "Enjoo" (>0.99), "Febre" is orthogonal to both (0.0).
_FAKE_VECTORS = {
    "Enjoo": [1.0, 0.0, 0.0],
    "Náusea": [0.99, 0.01, 0.0],
    "Febre": [0.0, 1.0, 0.0],
}


def _fake_embed(labels, *, api_key):
    return [_FAKE_VECTORS[label] for label in labels]


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def make_user_and_report(db, *, symptom_description="Sintoma"):
    user = User(name="Paciente", email=f"p-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)

    now = datetime.now(timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        had_symptoms=True,
        symptom_description=symptom_description,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return user, report


def add_term(db, label):
    term = SymptomTerm(label=label)
    db.add(term)
    db.commit()
    db.refresh(term)
    return term


def link(db, *, report, patient_id, term):
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=patient_id))
    db.commit()


def test_cosine_similarity_of_identical_vectors_is_one():
    assert SymptomTermDedupService._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert SymptomTermDedupService._cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_find_duplicate_clusters_returns_empty_with_fewer_than_two_terms(monkeypatch):
    monkeypatch.setattr(SymptomTermDedupService, "_embed", staticmethod(_fake_embed))
    db = build_session()
    add_term(db, "Enjoo")

    assert SymptomTermDedupService.find_duplicate_clusters(db, api_key="test-key") == []


def test_find_duplicate_clusters_groups_near_duplicates_and_leaves_others_out(monkeypatch):
    monkeypatch.setattr(SymptomTermDedupService, "_embed", staticmethod(_fake_embed))
    db = build_session()
    add_term(db, "Enjoo")
    add_term(db, "Náusea")
    add_term(db, "Febre")

    clusters = SymptomTermDedupService.find_duplicate_clusters(db, api_key="test-key")

    assert len(clusters) == 1
    cluster = clusters[0]
    assert {cluster.canonical.label, *[d.label for d in cluster.duplicates]} == {"Enjoo", "Náusea"}
    assert cluster.similarity > 0.9


def test_find_duplicate_clusters_picks_the_more_used_term_as_canonical(monkeypatch):
    monkeypatch.setattr(SymptomTermDedupService, "_embed", staticmethod(_fake_embed))
    db = build_session()
    enjoo = add_term(db, "Enjoo")
    nausea = add_term(db, "Náusea")
    user, report_a = make_user_and_report(db)
    _, report_b = make_user_and_report(db)
    _, report_c = make_user_and_report(db)
    # "Náusea" has more usages than "Enjoo" -- it should become canonical
    # even though "Enjoo" was created first.
    link(db, report=report_a, patient_id=user.id, term=nausea)
    link(db, report=report_b, patient_id=user.id, term=nausea)
    link(db, report=report_c, patient_id=user.id, term=enjoo)

    clusters = SymptomTermDedupService.find_duplicate_clusters(db, api_key="test-key")

    assert clusters[0].canonical.label == "Náusea"
    assert [d.label for d in clusters[0].duplicates] == ["Enjoo"]


def test_merge_repoints_links_and_deletes_the_duplicate_term():
    db = build_session()
    enjoo = add_term(db, "Enjoo")
    nausea = add_term(db, "Náusea")
    user, report = make_user_and_report(db)
    link(db, report=report, patient_id=user.id, term=enjoo)

    cluster = DuplicateCluster(canonical=nausea, duplicates=(enjoo,), similarity=0.999)
    SymptomTermDedupService.merge(db, cluster)

    links = db.query(DailyReportSymptomTerm).filter(DailyReportSymptomTerm.daily_report_id == report.id).all()
    assert [link_.symptom_term_id for link_ in links] == [nausea.id]
    assert db.query(SymptomTerm).filter(SymptomTerm.id == enjoo.id).first() is None


def test_merge_drops_the_duplicate_link_instead_of_colliding_on_primary_key():
    db = build_session()
    enjoo = add_term(db, "Enjoo")
    nausea = add_term(db, "Náusea")
    user, report = make_user_and_report(db)
    # Same report already normalized to BOTH labels on separate occasions --
    # merging must not try to re-point the duplicate link onto a primary key
    # (daily_report_id, symptom_term_id) that's already taken by the
    # existing canonical link.
    link(db, report=report, patient_id=user.id, term=enjoo)
    link(db, report=report, patient_id=user.id, term=nausea)

    cluster = DuplicateCluster(canonical=nausea, duplicates=(enjoo,), similarity=0.999)
    SymptomTermDedupService.merge(db, cluster)

    links = db.query(DailyReportSymptomTerm).filter(DailyReportSymptomTerm.daily_report_id == report.id).all()
    assert [link_.symptom_term_id for link_ in links] == [nausea.id]
    assert db.query(SymptomTerm).filter(SymptomTerm.id == enjoo.id).first() is None
