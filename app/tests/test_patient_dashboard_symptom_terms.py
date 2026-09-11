from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MonitoringPlan,
    Role,
    RoleNameEnum,
    SymptomTerm,
    User,
    UserRole,
)
from app.services.patient_dashboard_service import PatientDashboardService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def get_or_create_patient_role(db) -> Role:
    role = db.query(Role).filter(Role.name == RoleNameEnum.PATIENT.value).first()
    if role is None:
        role = Role(name=RoleNameEnum.PATIENT.value)
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def create_patient(db, email: str = "paciente@example.com") -> User:
    user = User(name="Paciente", email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    role = get_or_create_patient_role(db)
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def create_report(db, *, user: User, report_date: date) -> DailyReport:
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == user.id).first()
    if plan is None:
        plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True)
        db.add(plan)
        db.commit()
        db.refresh(plan)

    now = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=True,
        had_symptoms=True,
        prompt_sent_at=now,
        expires_at=now,
        updated_at=now,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def link_term(db, *, report: DailyReport, patient_id: int, term: SymptomTerm) -> None:
    db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term.id, patient_id=patient_id))
    db.commit()


def test_top_symptom_terms_orders_by_frequency_desc():
    db = build_session()
    patient = create_patient(db)
    diarreia = SymptomTerm(label="Diarreia")
    cefaleia = SymptomTerm(label="Cefaleia")
    db.add_all([diarreia, cefaleia])
    db.commit()

    report_a = create_report(db, user=patient, report_date=date(2026, 1, 1))
    report_b = create_report(db, user=patient, report_date=date(2026, 1, 2))
    report_c = create_report(db, user=patient, report_date=date(2026, 1, 3))
    link_term(db, report=report_a, patient_id=patient.id, term=diarreia)
    link_term(db, report=report_b, patient_id=patient.id, term=diarreia)
    link_term(db, report=report_c, patient_id=patient.id, term=cefaleia)

    result = PatientDashboardService(db).get_top_symptom_terms(patient)

    assert [item.label for item in result.items] == ["Diarreia", "Cefaleia"]
    assert [item.count for item in result.items] == [2, 1]


def test_top_symptom_terms_respects_limit():
    db = build_session()
    patient = create_patient(db)
    terms = [SymptomTerm(label=f"Termo {index}") for index in range(3)]
    db.add_all(terms)
    db.commit()
    for index, term in enumerate(terms):
        report = create_report(db, user=patient, report_date=date(2026, 1, index + 1))
        link_term(db, report=report, patient_id=patient.id, term=term)

    result = PatientDashboardService(db).get_top_symptom_terms(patient, limit=2)

    assert len(result.items) == 2


def test_top_symptom_terms_scoped_to_patient():
    db = build_session()
    patient = create_patient(db, email="paciente@example.com")
    other_patient = create_patient(db, email="outro@example.com")
    term = SymptomTerm(label="Diarreia")
    db.add(term)
    db.commit()

    other_report = create_report(db, user=other_patient, report_date=date(2026, 1, 1))
    link_term(db, report=other_report, patient_id=other_patient.id, term=term)

    result = PatientDashboardService(db).get_top_symptom_terms(patient)

    assert result.items == []


def test_top_symptom_terms_empty_when_no_reports():
    db = build_session()
    patient = create_patient(db)

    result = PatientDashboardService(db).get_top_symptom_terms(patient)

    assert result.items == []
