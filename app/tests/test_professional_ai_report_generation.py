from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    AiReportCache,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    User,
    UserRole,
)
from app.services import professional_service as professional_service_module
from app.services.professional_service import ProfessionalService


class FakeInsightService:
    def __init__(self, api_key=None, modo=None):
        self.modo = modo

    def gerar_interpretacao(self, clinical_summary):
        return {"resumo": clinical_summary, "modo": self.modo}


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_professional_with_patient(db):
    professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
    professional = User(name="Dra. Ana", email="ana@example.com")
    db.add_all([professional_role, professional])
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=True, free_until=date(2099, 1, 1))
    db.add(profile)
    db.flush()

    patient = User(name="Paciente", email="paciente@example.com")
    db.add(patient)
    db.flush()
    plan = MonitoringPlan(patient_id=patient.id, title="Acompanhamento", active=True)
    db.add(plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, active=True))
    db.commit()
    return professional, patient


def test_generate_ai_report_creates_and_reuses_cached_report(monkeypatch):
    # Regression test: generate_ai_report used to reference
    # AiReportClinicalService without importing it, which raised NameError
    # the moment this (deprecated but still-mounted) endpoint was hit --
    # nothing exercised this code path before.
    monkeypatch.setattr(professional_service_module, "InsightService", FakeInsightService)
    db = build_session()
    professional, patient = create_professional_with_patient(db)
    service = ProfessionalService(db)

    first = service.generate_ai_report(
        professional, patient.id, periodo="semanal", modo="avaliacao_clinica", api_key=None
    )

    assert first.patient_id == patient.id
    assert first.ai == {"resumo": first.clinical_summary, "modo": "avaliacao_clinica"}
    assert db.query(AiReportCache).count() == 1

    second = service.generate_ai_report(
        professional, patient.id, periodo="semanal", modo="avaliacao_clinica", api_key=None
    )

    # Same week -> reuses the cached report instead of calling InsightService again.
    assert second.clinical_summary == first.clinical_summary
    assert db.query(AiReportCache).count() == 1
