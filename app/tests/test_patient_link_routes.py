from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import ProfessionalProfile, Role, RoleNameEnum, User, UserRole
from app.routes import patient_link_routes, professional_routes


def build_app(db, current_user):
    app = FastAPI()
    app.include_router(professional_routes.router, prefix="/professional")
    app.include_router(patient_link_routes.router, prefix="/patient-links")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def build_db_with_professional_and_patient():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()

    professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
    patient_role = Role(name=RoleNameEnum.PATIENT.value)
    db.add_all([professional_role, patient_role])
    db.flush()

    professional = User(name="Dra. Ana", email="ana@example.com")
    patient = User(name="Paciente", email="paciente@example.com", phone="5511999990000")
    db.add_all([professional, patient])
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    db.add(UserRole(user_id=patient.id, role_id=patient_role.id))
    db.add(ProfessionalProfile(user_id=professional.id, active=True))
    db.commit()
    db.refresh(professional)
    db.refresh(patient)
    return db, professional, patient


def test_professional_can_create_and_list_link_requests():
    db, professional, patient = build_db_with_professional_and_patient()
    client = build_app(db, professional)

    create_response = client.post("/professional/patient-links", json={"email": patient.email})
    assert create_response.status_code == 201
    assert create_response.json()["status"] == "PENDING"

    list_response = client.get("/professional/patient-links")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_patient_can_list_and_accept_link_request():
    db, professional, patient = build_db_with_professional_and_patient()
    professional_client = build_app(db, professional)
    create_response = professional_client.post("/professional/patient-links", json={"email": patient.email})
    request_id = create_response.json()["id"]

    patient_client = build_app(db, patient)
    incoming = patient_client.get("/patient-links")
    assert incoming.status_code == 200
    assert len(incoming.json()) == 1
    assert incoming.json()[0]["professional_name"] == professional.name

    respond = patient_client.post(f"/patient-links/{request_id}/respond", json={"accept": True})
    assert respond.status_code == 200
    assert respond.json()["status"] == "ACCEPTED"

    # No longer pending once accepted.
    incoming_after = patient_client.get("/patient-links")
    assert incoming_after.json() == []
