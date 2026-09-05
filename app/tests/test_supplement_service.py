from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import Supplement, SupplementDosagePeriodEnum, User
from app.services.supplement_service import SupplementService


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


def test_is_active_true_for_indeterminate_supplement():
    supplement = Supplement(patient_id=1, name="Ferro", started_at=date(2020, 1, 1), duration_days=None)

    assert SupplementService.is_active(supplement, today=date(2099, 1, 1)) is True


def test_is_active_true_within_duration_window():
    supplement = Supplement(patient_id=1, name="Amoxicilina", started_at=date(2026, 1, 1), duration_days=10)

    assert SupplementService.is_active(supplement, today=date(2026, 1, 5)) is True


def test_is_active_false_after_duration_elapses():
    supplement = Supplement(patient_id=1, name="Amoxicilina", started_at=date(2026, 1, 1), duration_days=10)

    assert SupplementService.is_active(supplement, today=date(2026, 1, 15)) is False


def test_list_active_names_excludes_expired_courses():
    today = date(2026, 6, 1)
    active = Supplement(patient_id=1, name="Vitamina D", started_at=today - timedelta(days=1), duration_days=None)
    expired = Supplement(patient_id=1, name="Amoxicilina", started_at=today - timedelta(days=20), duration_days=10)

    assert SupplementService.list_active_names([active, expired], today=today) == ["Vitamina D"]


def test_create_persists_dosage_schedule():
    db = build_session()
    patient = create_patient(db)

    supplement = SupplementService(db).create(
        patient,
        "Amoxicilina",
        dosage_times=3,
        dosage_period=SupplementDosagePeriodEnum.WEEK,
        duration_days=10,
    )

    assert supplement.dosage_times == 3
    assert supplement.dosage_period == "WEEK"
    assert supplement.duration_days == 10
    assert supplement.started_at == date.today()


def test_create_defaults_to_daily_indeterminate():
    db = build_session()
    patient = create_patient(db)

    supplement = SupplementService(db).create(patient, "Vitamina D")

    assert supplement.dosage_times == 1
    assert supplement.dosage_period == "DAY"
    assert supplement.duration_days is None
