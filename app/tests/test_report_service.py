from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MonitoringPlan,
    SymptomTerm,
    User,
)
from app.services.report_service import ReportService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def create_user_and_plan(db):
    user = User(name="Paciente", email="paciente@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)

    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True, start_date=date.today())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return user, plan


def create_completed_report(db, *, user, plan, symptom, created_at):
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=created_at.date(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        symptom_description=symptom,
        suspected_cause="teste",
        had_symptoms=True,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        prompt_sent_at=created_at,
        expires_at=created_at + timedelta(hours=24),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(report)
    db.commit()
    return report


def create_negative_report(db, *, user, plan, report_date):
    prompt_sent_at = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.NIGHT,
        status=DailyReportStatusEnum.COMPLETED,
        symptom_description=None,
        suspected_cause=None,
        had_symptoms=False,
        completed=True,
        awaiting_response=False,
        awaiting_cause=False,
        prompt_sent_at=prompt_sent_at,
        expires_at=prompt_sent_at + timedelta(hours=24),
        created_at=prompt_sent_at,
        updated_at=prompt_sent_at,
    )
    db.add(report)
    db.commit()
    return report


def test_report_service_supports_diario_period():
    db = build_session()
    user, plan = create_user_and_plan(db)
    now = datetime.now(timezone.utc)

    create_completed_report(db, user=user, plan=plan, symptom="Dor atual", created_at=now - timedelta(hours=12))
    create_completed_report(db, user=user, plan=plan, symptom="Dor anterior", created_at=now - timedelta(hours=36))
    create_completed_report(db, user=user, plan=plan, symptom="Dor antiga", created_at=now - timedelta(days=3))

    relatorio = ReportService(db).gerar_relatorio(user.id, "diario")

    assert "Dor atual".lower() in relatorio
    assert "Dor anterior".lower() in relatorio
    assert "Dor antiga".lower() not in relatorio
    assert "Período analisado" in relatorio


def test_report_service_includes_adherence_and_negative_checkins():
    db = build_session()
    user, plan = create_user_and_plan(db)
    today = datetime.now(timezone.utc).date()

    create_completed_report(
        db,
        user=user,
        plan=plan,
        symptom="Tontura",
        created_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
    )
    create_negative_report(db, user=user, plan=plan, report_date=today)

    relatorio = ReportService(db).gerar_relatorio(user.id, "semanal")

    assert "Check-ins respondidos: 2" in relatorio
    assert "Dias/check-ins com sintomas: 1" in relatorio
    assert "Dias/check-ins sem sintomas: 1" in relatorio
    assert "Taxa de adesão: 100.0%" in relatorio


def test_report_service_groups_by_normalized_term_instead_of_raw_text():
    # Without this, a continuation answer like "mesma dor, mesmo lugar"
    # would show up as its own unrelated-looking line in the exact text fed
    # to the AI clinical-assessment prompt, instead of adding to the
    # existing symptom's count.
    db = build_session()
    user, plan = create_user_and_plan(db)
    today = datetime.now(timezone.utc).date()

    day1 = create_completed_report(
        db, user=user, plan=plan, symptom="Dor de cabeça",
        created_at=datetime.combine(today - timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc),
    )
    day2 = create_completed_report(
        db, user=user, plan=plan, symptom="Mesma dor, mesmo lugar",
        created_at=datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
    )
    day3 = create_completed_report(
        db, user=user, plan=plan, symptom="Ainda a mesma dor",
        created_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
    )

    term = SymptomTerm(label="Cefaleia")
    db.add(term)
    db.commit()
    db.add_all([
        DailyReportSymptomTerm(daily_report_id=day1.id, symptom_term_id=term.id, patient_id=user.id, streak_days=1),
        # day2/day3 chain to day1 -- the report that first described the
        # symptom in detail -- exactly what SymptomNormalizationService
        # would set for a real continuation.
        DailyReportSymptomTerm(
            daily_report_id=day2.id, symptom_term_id=term.id, patient_id=user.id,
            streak_days=2, origin_report_id=day1.id,
        ),
        DailyReportSymptomTerm(
            daily_report_id=day3.id, symptom_term_id=term.id, patient_id=user.id,
            streak_days=3, origin_report_id=day1.id,
        ),
    ])
    db.commit()

    relatorio = ReportService(db).gerar_relatorio(user.id, "semanal")

    assert "Mesma dor, mesmo lugar" not in relatorio
    assert "Ainda a mesma dor" not in relatorio
    # The AI-facing text carries the ORIGIN description (day1's, the
    # detailed one) alongside the term, not just the short clinical label.
    assert "- Cefaleia (Dor de cabeça): 3 ocorrência(s), persistente por até 3 dias seguidos" in relatorio


def test_report_service_falls_back_to_raw_text_without_a_normalized_term():
    db = build_session()
    user, plan = create_user_and_plan(db)
    now = datetime.now(timezone.utc)

    create_completed_report(db, user=user, plan=plan, symptom="Dor no cotovelo", created_at=now)

    relatorio = ReportService(db).gerar_relatorio(user.id, "semanal")

    assert "- dor no cotovelo: 1 ocorrência(s)" in relatorio
    assert "persistente" not in relatorio
