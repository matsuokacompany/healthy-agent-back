from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.access_policy import AccessPolicy
from app.db.base import Base
from app.models.models import (
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    User,
    UserRole,
)


def build_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def user_with_role(db, *, name: str, email: str, role: RoleNameEnum) -> User:
    user = User(name=name, email=email)
    db.add(user)
    db.flush()
    role_record = db.query(Role).filter(Role.name == role.value).first()
    if not role_record:
        role_record = Role(name=role.value)
        db.add(role_record)
        db.flush()
    db.add(UserRole(user_id=user.id, role_id=role_record.id))
    db.commit()
    db.refresh(user)
    return user


def test_patient_can_only_read_self():
    db = build_db()
    patient = user_with_role(db, name="Paciente", email="patient@example.com", role=RoleNameEnum.PATIENT)
    other = user_with_role(db, name="Outro", email="other@example.com", role=RoleNameEnum.PATIENT)

    assert AccessPolicy(db, patient).require_patient_read(patient.id).id == patient.id
    with pytest.raises(HTTPException) as exc_info:
        AccessPolicy(db, patient).require_patient_read(other.id)
    assert exc_info.value.status_code == 403


def test_professional_can_only_read_actively_linked_patient():
    db = build_db()
    professional = user_with_role(
        db,
        name="Profissional",
        email="professional@example.com",
        role=RoleNameEnum.PROFESSIONAL,
    )
    linked_patient = user_with_role(
        db,
        name="Paciente vinculado",
        email="linked@example.com",
        role=RoleNameEnum.PATIENT,
    )
    other_patient = user_with_role(
        db,
        name="Paciente externo",
        email="external@example.com",
        role=RoleNameEnum.PATIENT,
    )
    profile = ProfessionalProfile(user_id=professional.id, active=True)
    plan = MonitoringPlan(patient_id=linked_patient.id, title="Plano", active=True)
    db.add_all([profile, plan])
    db.flush()
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=plan.id,
            professional_profile_id=profile.id,
            active=True,
        )
    )
    db.commit()

    policy = AccessPolicy(db, professional)
    assert policy.require_professional_patient_read(linked_patient.id).id == linked_patient.id
    with pytest.raises(HTTPException) as exc_info:
        policy.require_professional_patient_read(other_patient.id)
    assert exc_info.value.status_code == 403


def test_inactive_link_does_not_grant_professional_access():
    db = build_db()
    professional = user_with_role(
        db,
        name="Profissional",
        email="professional-inactive@example.com",
        role=RoleNameEnum.PROFESSIONAL,
    )
    patient = user_with_role(
        db,
        name="Paciente",
        email="inactive-patient@example.com",
        role=RoleNameEnum.PATIENT,
    )
    profile = ProfessionalProfile(user_id=professional.id, active=True)
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True)
    db.add_all([profile, plan])
    db.flush()
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=plan.id,
            professional_profile_id=profile.id,
            active=False,
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        AccessPolicy(db, professional).require_professional_patient_read(patient.id)
    assert exc_info.value.status_code == 403
