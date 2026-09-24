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


def create_report(db, *, patient, report_date, red_flag_category=None, completed=True, had_symptoms=True):
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).first()
    now = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    report = DailyReport(
        user_id=patient.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED if completed else DailyReportStatusEnum.PENDING,
        completed=completed,
        had_symptoms=had_symptoms,
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
    assert overview.adherence == []
    assert overview.symptoms_by_month == []


def test_dashboard_overview_computes_per_patient_adherence():
    db = build_session()
    professional, profile = create_professional(db)
    patient_a = create_monitored_patient(db, profile, name="Maria", email="maria@example.com")
    patient_b = create_monitored_patient(db, profile, name="João", email="joao@example.com")
    today = date.today()
    create_report(db, patient=patient_a, report_date=today, completed=True)
    create_report(db, patient=patient_a, report_date=today - timedelta(days=1), completed=False)
    create_report(db, patient=patient_b, report_date=today, completed=True)

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    by_patient = {entry.patient_id: entry for entry in overview.adherence}
    assert by_patient[patient_a.id].patient_name == "Maria"
    assert by_patient[patient_a.id].adherence_percentage == 50.0
    assert by_patient[patient_b.id].adherence_percentage == 100.0
    # Both reports fall in the same 7-day bucket (today and yesterday), so
    # patient_a's single weekly point should already reflect the 50% split.
    assert len(by_patient[patient_a.id].weekly) == 1
    assert by_patient[patient_a.id].weekly[0].adherence_percentage == 50.0


def test_dashboard_overview_buckets_adherence_into_weekly_points():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_monitored_patient(db, profile)
    today = date.today()
    create_report(db, patient=patient, report_date=today, completed=True)
    create_report(db, patient=patient, report_date=today - timedelta(days=10), completed=False)

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    entry = next(item for item in overview.adherence if item.patient_id == patient.id)
    assert len(entry.weekly) == 2
    assert entry.weekly[0].week_start < entry.weekly[1].week_start
    assert entry.weekly[0].adherence_percentage == 0.0
    assert entry.weekly[1].adherence_percentage == 100.0


def test_dashboard_overview_excludes_adherence_reports_outside_the_window():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_monitored_patient(db, profile)
    old_date = date.today() - timedelta(days=ProfessionalService.DASHBOARD_ADHERENCE_WINDOW_DAYS + 5)
    create_report(db, patient=patient, report_date=old_date, completed=False)

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    assert overview.adherence == [] or all(entry.patient_id != patient.id for entry in overview.adherence)


def test_dashboard_overview_buckets_symptom_counts_by_month():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_monitored_patient(db, profile)
    today = date.today()
    create_report(db, patient=patient, report_date=today, had_symptoms=True)
    create_report(db, patient=patient, report_date=today - timedelta(days=1), had_symptoms=False)

    overview = ProfessionalService(db).get_dashboard_overview(professional)

    current_month = today.strftime("%Y-%m")
    matching = [entry for entry in overview.symptoms_by_month if entry.month == current_month]
    assert len(matching) == 1
    assert matching[0].count == 1
