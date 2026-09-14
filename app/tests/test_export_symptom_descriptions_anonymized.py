import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.clinical_encryption import ClinicalEncryptionService, LocalDataKeyProvider
from app.db.base_class import Base
from app.models.models import Anamnese, CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
from app.scripts.export_symptom_descriptions_anonymized import export_symptom_descriptions
from app.services.clinical_data_service import ClinicalDataService


def _clinical_data() -> ClinicalDataService:
    # Plaintext-written test rows have no encryption envelope, so read_text
    # never actually decrypts anything here -- this just needs to construct
    # without AWS credentials, matching test_clinical_data_service.py's
    # pattern for the same reason.
    encryption = ClinicalEncryptionService(LocalDataKeyProvider(b"k" * 32), active_key_version="v1")
    return ClinicalDataService(encryption)


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def make_report(db, *, name, email, symptom_description, had_symptoms=True, phone=None, **risk_factors):
    user = User(name=name, email=email, phone=phone)
    db.add(user)
    db.commit()
    db.refresh(user)
    if risk_factors:
        db.add(Anamnese(user_id=user.id, **risk_factors))
        db.commit()
    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)

    now = datetime.now(timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        had_symptoms=had_symptoms,
        symptom_description=symptom_description if had_symptoms else None,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    return user, report


def test_export_only_includes_completed_symptomatic_reports():
    db = build_session()
    make_report(db, name="Ana", email="ana@example.com", symptom_description="Dor de cabeça forte")
    make_report(db, name="Bia", email="bia@example.com", symptom_description=None, had_symptoms=False)

    cases = export_symptom_descriptions(db, limit=100, clinical_data=_clinical_data())

    assert len(cases) == 1
    assert cases[0]["texto"] == "Dor de cabeça forte"


def test_export_never_includes_patient_identity():
    db = build_session()
    make_report(
        db,
        name="Carla Confidencial",
        email="carla-secreta@example.com",
        phone="+5511988887777",
        symptom_description="Febre alta",
    )

    cases = export_symptom_descriptions(db, limit=100, clinical_data=_clinical_data())
    serialized = json.dumps(cases)

    assert "Carla" not in serialized
    assert "carla-secreta" not in serialized
    assert "988887777" not in serialized
    assert "user_id" not in cases[0]
    assert "patient_id" not in cases[0]


def test_export_includes_risk_factor_booleans_but_no_other_anamnese_data():
    db = build_session()
    make_report(
        db,
        name="Duda",
        email="duda@example.com",
        symptom_description="Falta de ar leve",
        risk_heart_disease=True,
        risk_diabetes=False,
    )

    cases = export_symptom_descriptions(db, limit=100, clinical_data=_clinical_data())

    assert cases[0]["fator_risco_presente"]["risk_heart_disease"] is True
    assert cases[0]["fator_risco_presente"]["risk_diabetes"] is False


def test_export_marks_every_case_as_unlabeled_and_unreviewed():
    db = build_session()
    make_report(db, name="Elis", email="elis@example.com", symptom_description="Tontura leve")

    cases = export_symptom_descriptions(db, limit=100, clinical_data=_clinical_data())

    assert cases[0]["categoria_esperada"] is None
    assert cases[0]["revisado_pelo_medico"] is False


def test_export_respects_the_limit():
    db = build_session()
    for i in range(5):
        make_report(db, name=f"Paciente {i}", email=f"p{i}@example.com", symptom_description=f"Sintoma {i}")

    cases = export_symptom_descriptions(db, limit=2, clinical_data=_clinical_data())

    assert len(cases) == 2
