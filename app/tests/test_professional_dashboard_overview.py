from datetime import date, datetime, timedelta, timezone

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

_GRANDFATHERED_FREE_UNTIL = date(2099, 1, 1)


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def get_or_create_role(db, name):
    role = db.query(Role).filter(Role.name == name).first()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def create_professional(db, *, name="Dra. Ana", email="ana@example.com"):
    professional_role = get_or_create_role(db, RoleNameEnum.PROFESSIONAL.value)
    professional = User(name=name, email=email)
    db.add(professional)
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=True, free_until=_GRANDFATHERED_FREE_UNTIL)
    db.add(profile)
    db.commit()
    db.refresh(professional)
    db.refresh(profile)
    return professional, profile


def create_monitored_patient(db, profile, *, name="Maria", email="maria@example.com"):
    patient = User(name=name, email=email)
    db.add(patient)
    db.flush()
    plan = MonitoringPlan(patient_id=patient.id, title="Acompanhamento", active=True)
    db.add(plan)
    db.flush()
    db.add(
        MonitoringProfessional(
            monitoring_plan_id=plan.id,
            professional_profile_id=profile.id,
            role="responsible",
            active=True,
        )
    )
    db.commit()
    return patient


def create_report(db, *, patient, report_date, red_flag_category=None):
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).first()
    now = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    report = DailyReport(
        user_id=patient.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        had_symptoms=True,
        red_flag_category=red_flag_category,
        prompt_sent_at=now,
        expires_at=now,
        updated_at=now,
    )
    db.add(report)
    db.commit()
    return report


def test_dashboard_overview_lists_recent_red_flags_across_patients():
    db = build_session()
    professional, profile = create_professional(db)
    patient_a = create_monitored_patient(db, profile, name="Maria", email="maria@example.com")
    patient_b = create_monitored_patient(db, profile, name="João", email="joao@example.com")
    today = date.today()
    create_report(db, patient=patient_a, report_date=today, red_flag_category="cardiorrespiratorio")
    create_report(db, patient=patient_b, report_date=today - timedelta(days=1))

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    assert overview.active_patients == 2
    assert len(overview.red_flags) == 1
    assert overview.red_flags[0].patient_id == patient_a.id
    assert overview.red_flags[0].patient_name == "Maria"
    assert overview.red_flags[0].category_key == "cardiorrespiratorio"
    assert overview.red_flags[0].tier == "absoluto"


def test_dashboard_overview_excludes_red_flags_outside_the_lookback_window():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_monitored_patient(db, profile)
    old_date = date.today() - timedelta(days=ProfessionalService.DASHBOARD_RED_FLAG_LOOKBACK_DAYS + 5)
    create_report(db, patient=patient, report_date=old_date, red_flag_category="cardiorrespiratorio")

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    assert overview.red_flags == []


def test_dashboard_overview_excludes_other_professionals_patients():
    db = build_session()
    professional, profile = create_professional(db)
    _other_professional, other_profile = create_professional(db, name="Dr. Bruno", email="bruno@example.com")
    other_patient = create_monitored_patient(db, other_profile, name="Paciente de outra", email="outro@example.com")
    create_report(db, patient=other_patient, report_date=date.today(), red_flag_category="cardiorrespiratorio")

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    assert overview.active_patients == 0
    assert overview.red_flags == []


def test_dashboard_overview_empty_when_no_patients():
    db = build_session()
    professional, _ = create_professional(db)

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    assert overview.active_patients == 0
    assert overview.red_flags == []
    assert overview.top_symptoms == []
