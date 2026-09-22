from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    SymptomTerm,
    User,
    UserRole,
)
from app.services.patient_dashboard_service import PaginationParams, ReportFilters
from app.services.professional_service import ProfessionalService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_professional_and_patient(db, *, link=True):
    professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
    patient_role = Role(name=RoleNameEnum.PATIENT.value)
    professional = User(name="Dra. Ana", email="ana@example.com")
    patient = User(name="Maria Silva", email="maria@example.com")
    db.add_all([professional_role, patient_role, professional, patient])
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    db.add(UserRole(user_id=patient.id, role_id=patient_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=True, free_until=date(2099, 1, 1))
    db.add(profile)
    db.flush()
    plan = MonitoringPlan(patient_id=patient.id, title="Acompanhamento", active=True)
    db.add(plan)
    db.flush()
    if link:
        db.add(
            MonitoringProfessional(
                monitoring_plan_id=plan.id,
                professional_profile_id=profile.id,
                role="responsible",
                active=True,
            )
        )
    db.commit()
    db.refresh(professional)
    db.refresh(patient)
    db.refresh(plan)
    return professional, patient, plan


def test_get_checkins_surfaces_diet_and_medication_fields_for_the_day_detail_view():
    db = build_session()
    professional, patient, plan = create_professional_and_patient(db)
    now = datetime.now(timezone.utc)
    db.add(
        DailyReport(
            user_id=patient.id,
            monitoring_plan_id=plan.id,
            report_date=date.today(),
            check_type=CheckTypeEnum.MORNING,
            status=DailyReportStatusEnum.COMPLETED,
            completed=True,
            awaiting_response=False,
            awaiting_cause=False,
            had_symptoms=False,
            diet_adherence=False,
            lifestyle_notes="Comi um pedaço de bolo de chocolate no aniversário de um amigo",
            exercise_adherence=True,
            medication_adherence=False,
            medication_adherence_level="PARTIAL",
            prompt_sent_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )
    db.commit()

    result = ProfessionalService(db).get_checkins(
        professional,
        patient.id,
        pagination=PaginationParams(page=1, per_page=10),
        filters=ReportFilters(),
        order="desc",
    )

    assert len(result.items) == 1
    item = result.items[0]
    assert item.diet_adherence is False
    assert item.lifestyle_notes == "Comi um pedaço de bolo de chocolate no aniversário de um amigo"
    assert item.exercise_adherence is True
    assert item.medication_adherence is False
    assert item.medication_adherence_level == "PARTIAL"


def create_symptom_report(db, *, patient, plan, report_date, description, term_label):
    now = datetime.now(timezone.utc)
    report = DailyReport(
        user_id=patient.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        had_symptoms=True,
        symptom_description=description,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    term = db.query(SymptomTerm).filter(SymptomTerm.label == term_label).first()
    if term is None:
        term = SymptomTerm(label=term_label)
        db.add(term)
        db.commit()
        db.refresh(term)
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=patient.id))
    db.commit()
    return report


def test_get_top_symptom_terms_ranks_the_patients_most_reported_terms():
    db = build_session()
    professional, patient, plan = create_professional_and_patient(db)
    today = date.today()
    create_symptom_report(db, patient=patient, plan=plan, report_date=today - timedelta(days=3), description="Dor de cabeça", term_label="Cefaleia")
    create_symptom_report(db, patient=patient, plan=plan, report_date=today - timedelta(days=2), description="Dor de cabeça de novo", term_label="Cefaleia")
    create_symptom_report(db, patient=patient, plan=plan, report_date=today - timedelta(days=1), description="Enjoo", term_label="Náusea")

    response = ProfessionalService(db).get_top_symptom_terms(professional, patient.id, limit=6)

    assert [item.label for item in response.items] == ["Cefaleia", "Náusea"]
    assert response.items[0].count == 2
    assert response.items[1].count == 1


def test_get_top_symptom_terms_rejects_professional_without_link():
    db = build_session()
    professional, patient, _ = create_professional_and_patient(db, link=False)

    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService(db).get_top_symptom_terms(professional, patient.id)

    assert exc_info.value.status_code == 403


def _add_symptom_report(db, *, patient, plan, updated_at: datetime) -> DailyReport:
    report = DailyReport(
        user_id=patient.id,
        monitoring_plan_id=plan.id,
        report_date=updated_at.date(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        had_symptoms=True,
        awaiting_response=False,
        awaiting_cause=False,
        prompt_sent_at=updated_at,
        expires_at=updated_at + timedelta(hours=24),
        updated_at=updated_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_list_patients_symptom_count_is_not_limited_to_the_last_30_days():
    # Regression: the "Sintomas" column on /professional/patients used to
    # only count symptomatic check-ins from the last 30 days, while the
    # patient detail page's Check-ins tab, calendar and symptom-ranking
    # card show the full history with no such window -- any patient
    # monitored longer than a month showed a lower, confusing number here.
    db = build_session()
    professional, patient, plan = create_professional_and_patient(db)
    old = datetime.now(timezone.utc) - timedelta(days=90)
    _add_symptom_report(db, patient=patient, plan=plan, updated_at=old)

    items = {item.patient_id: item for item in ProfessionalService(db).list_patients(professional)}

    assert items[patient.id].symptom_reports_count == 1


def test_list_patients_symptom_count_covers_every_monitoring_plan_of_the_patient():
    # Regression: a patient can end up with more than one MonitoringPlan
    # row (e.g. a self-service -> professional conversion, or a relink
    # creating a new plan) while the old plan stays active=True. The old
    # per-plan count only ever reported whichever plan happened to have
    # the most recent check-in, silently dropping symptomatic reports
    # that were made under the other plan.
    db = build_session()
    professional, patient, old_plan = create_professional_and_patient(db)
    now = datetime.now(timezone.utc)
    _add_symptom_report(db, patient=patient, plan=old_plan, updated_at=now - timedelta(days=10))

    new_plan = MonitoringPlan(patient_id=patient.id, title="Novo acompanhamento", active=True)
    db.add(new_plan)
    db.flush()
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=new_plan.id,
            professional_profile_id=db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == professional.id).first().id,
            role="responsible",
            active=True,
        )
    )
    db.commit()
    db.refresh(new_plan)
    _add_symptom_report(db, patient=patient, plan=new_plan, updated_at=now)

    items = {item.patient_id: item for item in ProfessionalService(db).list_patients(professional)}

    assert items[patient.id].symptom_reports_count == 2
