import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    Anamnese,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    User,
    UserRole,
)
from app.models.schemas import ProfessionalPatientCreate, UserCreate
from app.services import professional_service as professional_service_module
from app.services.professional_service import ProfessionalService
from app.services.user_service import UserService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_professional(db):
    professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
    patient_role = Role(name=RoleNameEnum.PATIENT.value)
    professional = User(name="Dra. Ana", email="ana@example.com")
    db.add_all([professional_role, patient_role, professional])
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=True)
    db.add(profile)
    db.commit()
    db.refresh(professional)
    db.refresh(profile)
    return professional, profile


def patient_payload(**overrides):
    data = {
        "name": "Maria Silva",
        "email": "maria@example.com",
        "phone": "+55 (11) 99999-0000",
        "plan_title": "Acompanhamento inicial",
        "plan_description": "Check-ins diários",
        "plan_start_date": date(2026, 8, 13),
        "plan_end_date": date(2026, 9, 13),
    }
    data.update(overrides)
    return ProfessionalPatientCreate(**data)


def test_professional_creates_patient_plan_and_own_link_atomically(monkeypatch):
    invited_id = uuid.uuid4()
    monkeypatch.setattr(professional_service_module, "invite_supabase_user", lambda email, name=None: invited_id)
    db = build_session()
    professional, profile = create_professional(db)

    result = ProfessionalService(db).create_patient(professional, patient_payload())

    assert result.patient.email == "maria@example.com"
    assert result.patient.phone == "5511999990000"
    assert result.patient.roles == [RoleNameEnum.PATIENT.value]
    assert result.patient.supabase_user_id == invited_id
    assert result.monitoring_plan.patient_id == result.patient.id
    link = db.query(MonitoringProfessional).one()
    assert link.monitoring_plan_id == result.monitoring_plan.id
    assert link.professional_profile_id == profile.id
    assert link.role == "responsible"


def test_professional_creates_patient_when_supabase_invite_fails(monkeypatch):
    monkeypatch.setattr(professional_service_module, "invite_supabase_user", lambda email, name=None: None)
    db = build_session()
    professional, _ = create_professional(db)

    result = ProfessionalService(db).create_patient(professional, patient_payload())

    assert result.patient.supabase_user_id is None
    assert db.query(MonitoringPlan).count() == 1


def test_professional_patient_creation_rejects_duplicate_email():
    db = build_session()
    professional, _ = create_professional(db)
    db.add(User(name="Existing", email="maria@example.com"))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService(db).create_patient(professional, patient_payload())

    assert exc_info.value.status_code == 409
    assert db.query(MonitoringPlan).count() == 0


def test_professional_patient_creation_requires_active_profile():
    db = build_session()
    professional, profile = create_professional(db)
    profile.active = False
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService(db).create_patient(professional, patient_payload())

    assert exc_info.value.status_code == 403


def create_monitored_patient(db, profile):
    patient = User(name="Maria", email="maria.anamnese@example.com")
    db.add(patient)
    db.flush()
    plan = MonitoringPlan(patient_id=patient.id, title="Acompanhamento", active=True)
    db.add(plan)
    db.flush()
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=plan.id,
            professional_profile_id=profile.id,
            role="responsible",
            active=True,
        )
    )
    db.commit()
    return patient


def test_professional_creates_and_updates_monitored_patient_anamnese():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_monitored_patient(db, profile)
    service = ProfessionalService(db)

    created = service.create_anamnese(professional, patient.id, "Anamnese inicial")
    updated = service.update_anamnese(professional, patient.id, "Anamnese revisada")

    assert created.id == updated.id
    assert updated.info == "Anamnese revisada"
    assert db.query(Anamnese).filter(Anamnese.user_id == patient.id).count() == 1


def test_professional_cannot_create_anamnese_for_unmonitored_patient():
    db = build_session()
    professional, _ = create_professional(db)
    patient = User(name="Sem vínculo", email="sem-vinculo@example.com")
    db.add(patient)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService(db).create_anamnese(professional, patient.id, "Não autorizada")

    assert exc_info.value.status_code == 403


def test_professional_cannot_create_duplicate_patient_anamnese():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_monitored_patient(db, profile)
    service = ProfessionalService(db)
    service.create_anamnese(professional, patient.id, "Original")

    with pytest.raises(HTTPException) as exc_info:
        service.create_anamnese(professional, patient.id, "Duplicada")

    assert exc_info.value.status_code == 409


def test_admin_cannot_create_a_professional_user():
    db = build_session()
    admin = User(name="Admin", email="admin@example.com")
    admin.role_records = [Role(name=RoleNameEnum.ADMIN.value)]

    with pytest.raises(HTTPException) as exc_info:
        UserService(db).create_user(
            UserCreate(
                name="Novo Profissional",
                email="professional@example.com",
                roles=[RoleNameEnum.PROFESSIONAL],
            ),
            admin,
        )

    assert exc_info.value.status_code == 403
    assert "Only super admins" in exc_info.value.detail
