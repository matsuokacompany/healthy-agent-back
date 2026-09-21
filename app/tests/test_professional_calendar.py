from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    User,
    UserRole,
)
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


def test_get_calendar_returns_days_with_checkin_data():
    db = build_session()
    professional, patient, plan = create_professional_and_patient(db)
    db.add(
        DailyReport(
            user_id=patient.id,
            monitoring_plan_id=plan.id,
            report_date=date(2026, 3, 5),
            check_type=CheckTypeEnum.MORNING,
            status=DailyReportStatusEnum.COMPLETED,
            completed=True,
            had_symptoms=True,
            awaiting_response=False,
            awaiting_cause=False,
            prompt_sent_at=datetime(2026, 3, 5, 8, tzinfo=timezone.utc),
            expires_at=datetime(2026, 3, 6, 8, tzinfo=timezone.utc),
        )
    )
    db.commit()

    calendar = ProfessionalService(db).get_calendar(professional, patient.id, year=2026, month=3)

    assert calendar.year == 2026
    assert calendar.month == 3
    assert len(calendar.days) == 31
    day = next(day for day in calendar.days if day.date == date(2026, 3, 5))
    assert day.has_checkin is True
    assert day.completed is True
    assert day.has_symptoms is True
    other_day = next(day for day in calendar.days if day.date == date(2026, 3, 6))
    assert other_day.has_checkin is False


def test_get_calendar_surfaces_symptom_description_and_diet_lifestyle_notes():
    # The professional's day-detail modal reads these off each day's
    # checkins -- without them the modal can only show "Sim/Não", not what
    # the patient actually wrote (the symptom itself, or what they ate
    # outside the diet).
    db = build_session()
    professional, patient, plan = create_professional_and_patient(db)
    db.add(
        DailyReport(
            user_id=patient.id,
            monitoring_plan_id=plan.id,
            report_date=date(2026, 3, 5),
            check_type=CheckTypeEnum.MORNING,
            status=DailyReportStatusEnum.COMPLETED,
            completed=True,
            had_symptoms=True,
            symptom_description="Dor lateral direita da pelve",
            diet_adherence=False,
            lifestyle_notes="Comi um pedaço de bolo no aniversário de um amigo",
            awaiting_response=False,
            awaiting_cause=False,
            prompt_sent_at=datetime(2026, 3, 5, 8, tzinfo=timezone.utc),
            expires_at=datetime(2026, 3, 6, 8, tzinfo=timezone.utc),
        )
    )
    db.commit()

    calendar = ProfessionalService(db).get_calendar(professional, patient.id, year=2026, month=3)

    day = next(day for day in calendar.days if day.date == date(2026, 3, 5))
    assert len(day.checkins) == 1
    checkin = day.checkins[0]
    assert checkin.symptom_description == "Dor lateral direita da pelve"
    assert checkin.diet_adherence is False
    assert checkin.lifestyle_notes == "Comi um pedaço de bolo no aniversário de um amigo"


def test_get_calendar_rejects_professional_without_link():
    db = build_session()
    professional, patient, _ = create_professional_and_patient(db, link=False)

    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService(db).get_calendar(professional, patient.id, year=2026, month=3)

    assert exc_info.value.status_code == 403
