from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import Allergy, User
from app.routes import allergy_routes


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
    app.include_router(allergy_routes.router, prefix="/allergies")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: patient
    return TestClient(app), db, patient, other_patient


def test_patient_can_create_and_list_own_allergies():
    client, db, patient, _ = build_client()

    created = client.post("/allergies/", json={"allergen": "Frutos do mar", "severity": "RISCO_DE_MORTE"})
    assert created.status_code == 201
    assert created.json()["allergen"] == "Frutos do mar"
    assert created.json()["severity"] == "RISCO_DE_MORTE"

    listed = client.get("/allergies/me")
    assert listed.status_code == 200
    allergens = [item["allergen"] for item in listed.json()]
    assert allergens == ["Frutos do mar"]


def test_allergies_are_listed_in_creation_order():
    client, db, patient, _ = build_client()
    client.post("/allergies/", json={"allergen": "Amendoim"})
    client.post("/allergies/", json={"allergen": "Penicilina"})

    allergens = [item["allergen"] for item in client.get("/allergies/me").json()]
    assert allergens == ["Amendoim", "Penicilina"]


def test_create_allergy_defaults_to_moderada():
    client, _, _, _ = build_client()

    created = client.post("/allergies/", json={"allergen": "Poeira"}).json()

    assert created["severity"] == "MODERADA"


def test_patient_can_update_own_allergy():
    client, db, patient, _ = build_client()
    created = client.post("/allergies/", json={"allergen": "Amendoim", "severity": "LEVE"}).json()

    response = client.patch(f"/allergies/{created['id']}", json={"severity": "GRAVE"})

    assert response.status_code == 200
    body = response.json()
    assert body["allergen"] == "Amendoim"
    assert body["severity"] == "GRAVE"


def test_patient_can_delete_own_allergy():
    client, db, patient, _ = build_client()
    created = client.post("/allergies/", json={"allergen": "Amendoim"}).json()

    response = client.delete(f"/allergies/{created['id']}")
    assert response.status_code == 204
    assert client.get("/allergies/me").json() == []


def test_patient_cannot_update_another_patients_allergy():
    client, db, patient, other_patient = build_client()
    other_allergy = Allergy(patient_id=other_patient.id, allergen="Ferro")
    db.add(other_allergy)
    db.commit()
    db.refresh(other_allergy)

    response = client.patch(f"/allergies/{other_allergy.id}", json={"allergen": "Ferro quelato"})

    assert response.status_code == 404
    db.refresh(other_allergy)
    assert other_allergy.allergen == "Ferro"


def test_patient_cannot_delete_another_patients_allergy():
    client, db, patient, other_patient = build_client()
    other_allergy = Allergy(patient_id=other_patient.id, allergen="Ferro")
    db.add(other_allergy)
    db.commit()
    db.refresh(other_allergy)

    response = client.delete(f"/allergies/{other_allergy.id}")

    assert response.status_code == 404
    assert db.query(Allergy).filter(Allergy.id == other_allergy.id).count() == 1


def test_patient_only_sees_own_allergies():
    client, db, patient, other_patient = build_client()
    db.add(Allergy(patient_id=other_patient.id, allergen="Ferro"))
    db.commit()
    client.post("/allergies/", json={"allergen": "Amendoim"})

    allergens = [item["allergen"] for item in client.get("/allergies/me").json()]
    assert allergens == ["Amendoim"]


def test_create_allergy_rejects_blank_allergen():
    client, _, _, _ = build_client()

    response = client.post("/allergies/", json={"allergen": "   "})

    assert response.status_code == 422


def test_create_allergy_rejects_invalid_severity():
    client, _, _, _ = build_client()

    response = client.post("/allergies/", json={"allergen": "Amendoim", "severity": "MORTAL"})

    assert response.status_code == 422
