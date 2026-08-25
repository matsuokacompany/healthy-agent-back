from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_admin, get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import MonitoringPlan, MonitoringPlanOriginEnum, Role, RoleNameEnum, User, UserRole
from app.routes import anamnese_routes, monitoring_routes, self_monitoring_routes
from app.services.self_monitoring_service import SelfMonitoringService


def _deny_admin():
    raise HTTPException(status_code=403, detail="Admin privileges required")


def build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()

    patient_role = Role(name=RoleNameEnum.PATIENT.value)
    db.add(patient_role)
    db.flush()
    self_service_patient = User(name="Paciente Autonomo", email="autonomo@example.com", phone="5511999990000")
    db.add(self_service_patient)
    db.flush()
    db.add(UserRole(user_id=self_service_patient.id, role_id=patient_role.id))
    db.commit()
    db.refresh(self_service_patient)

    app = FastAPI()
    app.include_router(self_monitoring_routes.router, prefix="/self-monitoring")
    app.include_router(anamnese_routes.router, prefix="/anamneses")
    app.include_router(monitoring_routes.router, prefix="/monitoring")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: self_service_patient
    app.dependency_overrides[get_current_admin] = _deny_admin
    return TestClient(app), db, self_service_patient


def test_self_service_patient_can_create_own_plan():
    client, db, patient = build_client()

    response = client.post("/self-monitoring/plan")

    assert response.status_code == 201
    body = response.json()
    assert body["patient_id"] == patient.id
    assert body["origin"] == "SELF_SERVICE"
    assert body["title"] == "Automonitoramento"

    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).one()
    assert plan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value


def test_self_service_plan_creation_is_idempotent():
    client, db, patient = build_client()

    first = client.post("/self-monitoring/plan").json()
    second = client.post("/self-monitoring/plan").json()

    assert first["id"] == second["id"]
    assert db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).count() == 1


def test_self_service_patient_can_get_evolution_report():
    client, _, _ = build_client()
    client.post("/self-monitoring/plan")

    response = client.get("/self-monitoring/evolution-report")

    assert response.status_code == 200
    body = response.json()
    assert body["period_days"] == 30
    assert body["metrics"]["total_checkins"] == 0


def test_self_service_patient_cannot_create_anamnese_via_generic_route():
    client, _, patient = build_client()

    response = client.post("/anamneses/", json={"user_id": patient.id, "info": "auto-relato"})

    assert response.status_code == 403


def test_self_service_patient_cannot_use_generic_monitoring_plan_endpoint():
    client, _, patient = build_client()

    response = client.post(
        "/monitoring/plans",
        json={"title": "Plano manual", "patient_id": patient.id, "active": True},
    )

    assert response.status_code == 403


def test_create_or_reactivate_plan_reuses_existing_active_plan():
    _, db, patient = build_client()
    service = SelfMonitoringService(db)

    first = service.create_or_reactivate_plan(patient)
    second = service.create_or_reactivate_plan(patient)

    assert first.id == second.id
    assert db.query(MonitoringPlan).count() == 1
