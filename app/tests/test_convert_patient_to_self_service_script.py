from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    MonitoringProfessional,
    ProfessionalProfile,
    User,
)
from app.scripts import convert_patient_to_self_service as script


class FakeSessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, _exc_type, _exc, _traceback):
        return False


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_linked_patient(db, *, email="patient@example.com"):
    patient = User(name="Paciente", email=email)
    professional = User(name="Dra. Ana", email="ana@example.com")
    db.add_all([patient, professional])
    db.flush()
    profile = ProfessionalProfile(user_id=professional.id, active=True)
    db.add(profile)
    db.flush()
    plan = MonitoringPlan(
        patient_id=patient.id,
        title="Acompanhamento profissional",
        active=True,
        origin=MonitoringPlanOriginEnum.PROFESSIONAL.value,
    )
    db.add(plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, active=True))
    db.commit()
    return patient, plan


def test_dry_run_makes_no_changes(monkeypatch):
    db = build_session()
    patient, plan = create_linked_patient(db)

    monkeypatch.setattr(script, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(script, "_parser", lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(email=patient.email, execute=False)))

    script.main()

    db.refresh(plan)
    assert plan.active is True
    assert db.query(MonitoringPlan).filter(MonitoringPlan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value).count() == 0


def test_execute_deactivates_professional_plan_and_creates_self_service(monkeypatch):
    db = build_session()
    patient, plan = create_linked_patient(db)

    monkeypatch.setattr(script, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(script, "_parser", lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(email=patient.email, execute=True)))

    script.main()

    db.refresh(plan)
    assert plan.active is False
    assert db.query(MonitoringProfessional).filter(MonitoringProfessional.monitoring_plan_id == plan.id, MonitoringProfessional.active.is_(True)).count() == 0

    self_service_plan = (
        db.query(MonitoringPlan)
        .filter(MonitoringPlan.patient_id == patient.id, MonitoringPlan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value)
        .first()
    )
    assert self_service_plan is not None
    assert self_service_plan.active is True


def test_execute_leaves_existing_self_service_plan_untouched(monkeypatch):
    db = build_session()
    patient, plan = create_linked_patient(db)
    existing_self_service = MonitoringPlan(
        patient_id=patient.id,
        title="Automonitoramento",
        active=True,
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
    )
    db.add(existing_self_service)
    db.commit()

    monkeypatch.setattr(script, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(script, "_parser", lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(email=patient.email, execute=True)))

    script.main()

    assert db.query(MonitoringPlan).filter(MonitoringPlan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value).count() == 1


def test_unknown_email_is_a_no_op(monkeypatch):
    db = build_session()

    monkeypatch.setattr(script, "SessionLocal", lambda: FakeSessionContext(db))
    monkeypatch.setattr(script, "_parser", lambda: SimpleNamespace(parse_args=lambda: SimpleNamespace(email="ghost@example.com", execute=True)))

    script.main()  # no exception

    assert db.query(MonitoringPlan).count() == 0
