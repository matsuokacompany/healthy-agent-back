import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    Anamnese,
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DietDocument,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    Supplement,
    SupplementDosagePeriodEnum,
    User,
)
from app.services.anamnese_clinical_service import AnamneseClinicalService
from app.services.patient_handoff_service import PatientHandoffService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_patient(db):
    patient = User(name="Paciente", email="patient@example.com", supabase_user_id=uuid.uuid4())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def test_summary_includes_anamnese_allergies_risk_factors_supplements_and_diet_document():
    db = build_session()
    patient = create_patient(db)

    anamnese = Anamnese(user_id=patient.id, risk_diabetes=True, risk_asthma_or_copd=False)
    db.add(anamnese)
    db.flush()
    AnamneseClinicalService.write(anamnese, "Histórico de hipertensão controlada.")
    AnamneseClinicalService.write_allergies(
        anamnese, {"medication_allergies": "Penicilina", "food_restrictions": "Amendoim"}
    )
    db.add(
        Supplement(
            patient_id=patient.id,
            name="Losartana",
            dosage_times=1,
            dosage_period=SupplementDosagePeriodEnum.DAY.value,
            started_at=date.today(),
        )
    )
    db.add(
        DietDocument(
            patient_id=patient.id,
            uploaded_by_user_id=patient.id,
            bucket="clinical-documents",
            object_key="patients/1/diet-plan/x.pdf",
            original_filename="plano-nutricional.pdf",
            byte_size=100,
            sha256="abc",
        )
    )
    db.commit()

    summary = PatientHandoffService(db).get_summary(patient, patient.id)

    assert summary.anamnese_info == "Histórico de hipertensão controlada."
    assert "Diabetes" in " ".join(summary.risk_factors) or any(
        "diabet" in label.lower() for label in summary.risk_factors
    )
    assert summary.medication_allergies == "Penicilina"
    assert summary.food_restrictions == "Amendoim"
    assert [s.name for s in summary.supplements] == ["Losartana"]
    assert summary.diet_document is not None
    assert summary.diet_document.original_filename == "plano-nutricional.pdf"
    assert summary.monitoring_summary is not None


def test_summary_handles_a_patient_with_no_anamnese_or_diet_document():
    db = build_session()
    patient = create_patient(db)

    summary = PatientHandoffService(db).get_summary(patient, patient.id)

    assert summary.anamnese_info is None
    assert summary.risk_factors == []
    assert summary.medication_allergies is None
    assert summary.food_restrictions is None
    assert summary.supplements == []
    assert summary.diet_document is None


def test_summary_monitoring_period_reflects_explicit_dates():
    db = build_session()
    patient = create_patient(db)
    plan = MonitoringPlan(
        patient_id=patient.id,
        title="Automonitoramento",
        active=True,
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
    )
    db.add(plan)
    db.commit()
    report_date = date.today() - timedelta(days=5)
    prompt_sent_at = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    db.add(
        DailyReport(
            user_id=patient.id,
            monitoring_plan_id=plan.id,
            report_date=report_date,
            check_type=CheckTypeEnum.MORNING,
            status=DailyReportStatusEnum.COMPLETED,
            completed=True,
            awaiting_response=False,
            awaiting_cause=False,
            prompt_sent_at=prompt_sent_at,
            expires_at=prompt_sent_at + timedelta(hours=24),
        )
    )
    db.commit()

    start = date.today() - timedelta(days=30)
    end = date.today()
    summary = PatientHandoffService(db).get_summary(patient, patient.id, start_date=start, end_date=end)

    assert summary.monitoring_summary.start_date == start
    assert summary.monitoring_summary.end_date == end


def test_summary_rejects_a_custom_period_shorter_than_the_thirty_day_minimum():
    db = build_session()
    patient = create_patient(db)

    start = date.today() - timedelta(days=10)
    end = date.today()
    with pytest.raises(HTTPException) as exc_info:
        PatientHandoffService(db).get_summary(patient, patient.id, start_date=start, end_date=end)

    assert exc_info.value.status_code == 422
