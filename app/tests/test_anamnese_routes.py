from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import Anamnese, MonitoringPlan, MonitoringPlanOriginEnum, Role, RoleNameEnum, User
from app.models.schemas import AnamneseBase, AnamneseCreate, AnamneseUpdate
from app.routes.anamnese_routes import create_anamnese, create_my_anamnese, update_my_anamnese


class FakeQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        self.db.query_count += 1
        if self.db.query_count == 1:
            return None
        return Anamnese(id=99, user_id=1, info="existing")


class FakeSession:
    def __init__(self):
        self.query_count = 0
        self.rolled_back = False

    def query(self, *args, **kwargs):
        return FakeQuery(self)

    def add(self, item):
        self.item = item

    def flush(self):
        # Real databases assign the primary key before clinical encryption.
        self.item.id = 100

    def commit(self):
        raise IntegrityError("insert", {}, Exception("unique violation"))

    def rollback(self):
        self.rolled_back = True


def test_create_anamnese_returns_conflict_when_unique_constraint_races(monkeypatch):
    db = FakeSession()
    current_user = User(id=1, name="Admin", email="admin@example.com")
    current_user.role_records = [Role(name=RoleNameEnum.ADMIN.value)]
    monkeypatch.setattr("app.routes.anamnese_routes.AnamneseClinicalService.write", lambda item, info: None)

    with pytest.raises(HTTPException) as exc:
        create_anamnese(
            anamnese=AnamneseCreate(user_id=1, info="nova"),
            db=db,
            current_user=current_user,
        )

    assert exc.value.status_code == 409
    assert db.rolled_back is True


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_patient(db):
    # A uuid4, not id(object()) -- CPython can reuse a just-freed object's id
    # for the next allocation, which collided on the users.email unique
    # constraint once enough other tests ran in the same process.
    patient = User(name="Paciente", email=f"patient-{uuid4()}@example.com")
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def link_professional_plan(db, patient):
    db.add(
        MonitoringPlan(
            patient_id=patient.id,
            title="Plano",
            active=True,
            start_date=date.today(),
            origin=MonitoringPlanOriginEnum.PROFESSIONAL.value,
        )
    )
    db.commit()


def test_self_service_patient_can_create_own_anamnese():
    db = build_session()
    patient = create_patient(db)

    result = create_anamnese(anamnese=AnamneseCreate(user_id=patient.id, info="Minha história"), db=db, current_user=patient)

    assert result.info == "Minha história"
    assert db.query(Anamnese).filter(Anamnese.user_id == patient.id).count() == 1


def test_self_service_patient_cannot_create_anamnese_for_another_user():
    db = build_session()
    patient = create_patient(db)
    other = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        create_anamnese(anamnese=AnamneseCreate(user_id=other.id, info="Não é meu"), db=db, current_user=patient)

    assert exc.value.status_code == 403


def test_professionally_monitored_patient_cannot_create_own_anamnese():
    db = build_session()
    patient = create_patient(db)
    link_professional_plan(db, patient)

    with pytest.raises(HTTPException) as exc:
        create_anamnese(anamnese=AnamneseCreate(user_id=patient.id, info="Tentando"), db=db, current_user=patient)

    assert exc.value.status_code == 403


def test_self_service_patient_can_create_own_anamnese_via_me_route():
    db = build_session()
    patient = create_patient(db)

    result = create_my_anamnese(payload=AnamneseBase(info="Minha história"), db=db, current_user=patient)

    assert result.info == "Minha história"
    assert db.query(Anamnese).filter(Anamnese.user_id == patient.id).count() == 1


def test_professionally_monitored_patient_cannot_create_own_anamnese_via_me_route():
    db = build_session()
    patient = create_patient(db)
    link_professional_plan(db, patient)

    with pytest.raises(HTTPException) as exc:
        create_my_anamnese(payload=AnamneseBase(info="Tentando"), db=db, current_user=patient)

    assert exc.value.status_code == 403


def test_self_service_patient_can_update_own_anamnese():
    db = build_session()
    patient = create_patient(db)
    create_anamnese(anamnese=AnamneseCreate(user_id=patient.id, info="Versão 1"), db=db, current_user=patient)

    updated = update_my_anamnese(payload=AnamneseUpdate(info="Versão 2"), db=db, current_user=patient)

    assert updated.info == "Versão 2"


def test_allergy_and_food_restriction_fields_round_trip_through_create_and_update():
    db = build_session()
    patient = create_patient(db)

    created = create_my_anamnese(
        payload=AnamneseBase(
            info="Versão 1",
            medication_allergies="Penicilina",
            food_restrictions="Lactose",
        ),
        db=db,
        current_user=patient,
    )
    assert created.medication_allergies == "Penicilina"
    assert created.food_restrictions == "Lactose"

    # Omitting the fields on update must leave them untouched.
    updated = update_my_anamnese(payload=AnamneseUpdate(info="Versão 2"), db=db, current_user=patient)
    assert updated.medication_allergies == "Penicilina"
    assert updated.food_restrictions == "Lactose"

    # An explicit null clears just that one field -- Pydantic tracks
    # "medication_allergies" as set here even though None is also its
    # default, so exclude_unset still picks it up.
    cleared = update_my_anamnese(
        payload=AnamneseUpdate(medication_allergies=None), db=db, current_user=patient
    )
    assert cleared.medication_allergies is None
    assert cleared.food_restrictions == "Lactose"


def test_professionally_monitored_patient_cannot_update_own_anamnese(monkeypatch):
    db = build_session()
    patient = create_patient(db)
    create_anamnese(anamnese=AnamneseCreate(user_id=patient.id, info="Versão 1"), db=db, current_user=patient)
    link_professional_plan(db, patient)

    with pytest.raises(HTTPException) as exc:
        update_my_anamnese(payload=AnamneseUpdate(info="Versão 2"), db=db, current_user=patient)

    assert exc.value.status_code == 403
