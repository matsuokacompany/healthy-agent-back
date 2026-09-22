import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import MonitoringPlan, MonitoringPlanOriginEnum, MonitoringProfessional, ProfessionalProfile, User
from app.models.schemas import MonitoringPlanRead


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_patient(db):
    patient = User(name="Paciente", email="paciente@example.com", supabase_user_id=uuid.uuid4())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def create_professional(db, *, name="Dra. Ana"):
    professional_user = User(name=name, email=f"{name.lower().replace(' ', '.')}@example.com", supabase_user_id=uuid.uuid4())
    db.add(professional_user)
    db.flush()
    profile = ProfessionalProfile(user_id=professional_user.id, specialty="Clínica geral", active=True)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def test_monitoring_plan_read_includes_the_active_responsible_professional():
    db = build_session()
    patient = create_patient(db)
    profile = create_professional(db)
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.PROFESSIONAL.value)
    db.add(plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, active=True))
    db.commit()
    db.refresh(plan)

    read = MonitoringPlanRead.model_validate(plan)

    assert [p.name for p in read.professionals] == ["Dra. Ana"]
    assert read.professionals[0].specialty == "Clínica geral"


def test_monitoring_plan_read_omits_an_inactive_professional_link():
    db = build_session()
    patient = create_patient(db)
    profile = create_professional(db)
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.PROFESSIONAL.value)
    db.add(plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, active=False))
    db.commit()
    db.refresh(plan)

    read = MonitoringPlanRead.model_validate(plan)

    assert read.professionals == []


def test_monitoring_plan_read_defaults_to_no_professionals():
    db = build_session()
    patient = create_patient(db)
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.SELF_SERVICE.value)
    db.add(plan)
    db.commit()
    db.refresh(plan)

    read = MonitoringPlanRead.model_validate(plan)

    assert read.professionals == []
