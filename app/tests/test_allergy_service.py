from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import AllergySeverityEnum, User
from app.services.allergy_service import AllergyService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_patient(db):
    patient = User(name="Paciente", email="patient@example.com")
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def test_create_persists_allergen_and_severity():
    db = build_session()
    patient = create_patient(db)

    allergy = AllergyService(db).create(patient, "Frutos do mar", severity=AllergySeverityEnum.RISCO_DE_MORTE)

    assert allergy.allergen == "Frutos do mar"
    assert allergy.severity == "RISCO_DE_MORTE"


def test_create_defaults_to_moderada():
    db = build_session()
    patient = create_patient(db)

    allergy = AllergyService(db).create(patient, "Poeira")

    assert allergy.severity == "MODERADA"


def test_list_for_patient_orders_by_creation():
    db = build_session()
    patient = create_patient(db)
    service = AllergyService(db)
    service.create(patient, "Amendoim")
    service.create(patient, "Penicilina")

    allergens = [allergy.allergen for allergy in service.list_for_patient(patient.id)]

    assert allergens == ["Amendoim", "Penicilina"]


def test_update_changes_severity():
    db = build_session()
    patient = create_patient(db)
    allergy = AllergyService(db).create(patient, "Amendoim", severity=AllergySeverityEnum.LEVE)

    updated = AllergyService(db).update(patient, allergy.id, severity=AllergySeverityEnum.GRAVE)

    assert updated.severity == "GRAVE"


def test_delete_removes_allergy():
    db = build_session()
    patient = create_patient(db)
    allergy = AllergyService(db).create(patient, "Amendoim")

    deleted = AllergyService(db).delete(patient, allergy.id)

    assert deleted is True
    assert AllergyService(db).list_for_patient(patient.id) == []
