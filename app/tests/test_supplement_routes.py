from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import Supplement, User
from app.routes import supplement_routes


def build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()

    patient = User(name="Paciente", email=f"p-{datetime.now().timestamp()}@example.com")
    other_patient = User(name="Outro Paciente", email=f"o-{datetime.now().timestamp()}@example.com")
    db.add_all([patient, other_patient])
    db.commit()
    db.refresh(patient)
    db.refresh(other_patient)

    app = FastAPI()
    app.include_router(supplement_routes.router, prefix="/supplements")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: patient
    return TestClient(app), db, patient, other_patient


def test_patient_can_create_and_list_own_supplements():
    client, db, patient, _ = build_client()

    created = client.post("/supplements/", json={"name": "Vitamina D"})
    assert created.status_code == 201
    assert created.json()["name"] == "Vitamina D"

    listed = client.get("/supplements/me")
    assert listed.status_code == 200
    names = [item["name"] for item in listed.json()]
    assert names == ["Vitamina D"]


def test_supplements_are_listed_in_creation_order():
    client, db, patient, _ = build_client()
    client.post("/supplements/", json={"name": "Vitamina D"})
    client.post("/supplements/", json={"name": "Ômega 3"})

    names = [item["name"] for item in client.get("/supplements/me").json()]
    assert names == ["Vitamina D", "Ômega 3"]


def test_patient_can_delete_own_supplement():
    client, db, patient, _ = build_client()
    created = client.post("/supplements/", json={"name": "Magnésio"}).json()

    response = client.delete(f"/supplements/{created['id']}")
    assert response.status_code == 204
    assert client.get("/supplements/me").json() == []


def test_patient_cannot_delete_another_patients_supplement():
    client, db, patient, other_patient = build_client()
    other_supplement = Supplement(patient_id=other_patient.id, name="Ferro")
    db.add(other_supplement)
    db.commit()
    db.refresh(other_supplement)

    response = client.delete(f"/supplements/{other_supplement.id}")

    assert response.status_code == 404
    assert db.query(Supplement).filter(Supplement.id == other_supplement.id).count() == 1


def test_patient_only_sees_own_supplements():
    client, db, patient, other_patient = build_client()
    db.add(Supplement(patient_id=other_patient.id, name="Ferro"))
    db.commit()
    client.post("/supplements/", json={"name": "Vitamina D"})

    names = [item["name"] for item in client.get("/supplements/me").json()]
    assert names == ["Vitamina D"]


def test_create_supplement_rejects_blank_name():
    client, _, _, _ = build_client()

    response = client.post("/supplements/", json={"name": "   "})

    assert response.status_code == 422


def test_create_supplement_defaults_to_daily_indeterminate():
    client, _, _, _ = build_client()

    created = client.post("/supplements/", json={"name": "Vitamina D"}).json()

    assert created["dosage_times"] == 1
    assert created["dosage_period"] == "DAY"
    assert created["duration_days"] is None
    assert created["started_at"] is not None


def test_create_supplement_accepts_custom_dosage_schedule():
    client, _, _, _ = build_client()

    created = client.post(
        "/supplements/",
        json={"name": "Amoxicilina", "dosage_times": 3, "dosage_period": "WEEK", "duration_days": 10},
    ).json()

    assert created["dosage_times"] == 3
    assert created["dosage_period"] == "WEEK"
    assert created["duration_days"] == 10
