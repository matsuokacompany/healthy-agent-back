from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User
from app.services.custom_report_service import CustomReportService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def create_user_and_plan(db, email: str = "paciente@example.com"):
    user = User(name="Paciente", email=email)
    db.add(user)
    db.commit()
    db.refresh(user)

    plan = MonitoringPlan(patient_id=user.id, title="Plano", active=True)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return user, plan


def create_report(
    db,
    *,
    user,
    plan,
    report_date: date,
    completed: bool,
    had_symptoms: bool | None = None,
    symptom_description: str | None = None,
):
    prompt_sent_at = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=report_date,
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED if completed else DailyReportStatusEnum.PENDING,
        symptom_description=symptom_description,
        had_symptoms=had_symptoms,
        completed=completed,
        awaiting_response=not completed,
        awaiting_cause=False,
        prompt_sent_at=prompt_sent_at,
        expires_at=prompt_sent_at + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    return report


def test_custom_summary_calculates_metrics_symptoms_gaps_and_weekly_timeline():
    db = build_session()
    user, plan = create_user_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)

    create_report(
        db,
        user=user,
        plan=plan,
        report_date=start_date,
        completed=True,
        had_symptoms=True,
        symptom_description="Dor de cabeça",
    )
    create_report(
        db,
        user=user,
        plan=plan,
        report_date=start_date + timedelta(days=1),
        completed=True,
        had_symptoms=True,
        symptom_description="  dor   de cabeça ",
    )
    create_report(
        db,
        user=user,
        plan=plan,
        report_date=start_date + timedelta(days=2),
        completed=True,
        had_symptoms=False,
    )
    create_report(
        db,
        user=user,
        plan=plan,
        report_date=start_date + timedelta(days=3),
        completed=False,
    )

    summary = CustomReportService(db).build_summary(user.id, start_date, end_date)

    assert summary.period_days == 30
    assert summary.aggregation == "weekly"
    assert summary.sufficient_data is False
    assert summary.metrics.total_checkins == 4
    assert summary.metrics.completed_checkins == 3
    assert summary.metrics.pending_checkins == 1
    assert summary.metrics.checkins_with_symptoms == 2
    assert summary.metrics.checkins_without_symptoms == 1
    assert summary.metrics.days_with_checkins == 4
    assert summary.metrics.adherence_percentage == 75.0
    assert summary.metrics.symptom_rate_percentage == 66.7
    assert summary.metrics.calendar_coverage_percentage == 13.3
    # The day-4 report exists (a check-in was sent) but was never completed,
    # so the real gap runs from the last *completed* response (day 2) to
    # end_date (day 29) — 27 days, not 26.
    assert summary.longest_gap_days == 27
    assert summary.symptom_trend == "insufficient_data"
    assert len(summary.symptoms) == 1
    assert summary.symptoms[0].description == "Dor de cabeça"
    assert summary.symptoms[0].occurrences == 2
    assert summary.symptoms[0].first_reported_at == start_date
    assert summary.symptoms[0].last_reported_at == start_date + timedelta(days=1)
    assert len(summary.timeline) == 5
    assert summary.timeline[0].start_date == start_date
    assert summary.timeline[0].end_date == start_date + timedelta(days=6)
    assert summary.timeline[-1].end_date == end_date


def test_custom_summary_marks_sufficient_data_and_detects_increasing_symptom_rate():
    db = build_session()
    user, plan = create_user_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)

    for offset in range(5):
        create_report(
            db,
            user=user,
            plan=plan,
            report_date=start_date + timedelta(days=offset),
            completed=True,
            had_symptoms=False,
        )
    for offset in range(20, 25):
        create_report(
            db,
            user=user,
            plan=plan,
            report_date=start_date + timedelta(days=offset),
            completed=True,
            had_symptoms=True,
            symptom_description="Tontura",
        )

    summary = CustomReportService(db).build_summary(user.id, start_date, end_date)

    assert summary.sufficient_data is True
    assert summary.metrics.completed_checkins == 10
    assert summary.symptom_trend == "increasing"


def test_longest_gap_days_ignores_pending_checkins_that_were_never_answered():
    # The scheduler creates a PENDING DailyReport every day a plan is
    # active, whether or not the patient responds — a pending row must not
    # count as "not a gap" or a patient who never answers would always show
    # a near-zero gap here.
    db = build_session()
    user, plan = create_user_and_plan(db)
    end_date = date.today()
    start_date = end_date - timedelta(days=29)

    create_report(db, user=user, plan=plan, report_date=start_date, completed=True, had_symptoms=False)
    for offset in range(1, 30):
        create_report(db, user=user, plan=plan, report_date=start_date + timedelta(days=offset), completed=False)

    summary = CustomReportService(db).build_summary(user.id, start_date, end_date)

    assert summary.longest_gap_days == 29


def test_custom_summary_uses_calendar_month_groups_for_period_up_to_one_year():
    db = build_session()
    user, _ = create_user_and_plan(db)
    start_date = date(2026, 1, 15)
    end_date = date(2026, 5, 14)

    summary = CustomReportService(db).build_summary(user.id, start_date, end_date)

    assert summary.aggregation == "monthly"
    assert len(summary.timeline) == 5
    assert summary.timeline[0].start_date == date(2026, 1, 15)
    assert summary.timeline[0].end_date == date(2026, 1, 31)
    assert summary.timeline[1].start_date == date(2026, 2, 1)
    assert summary.timeline[-1].end_date == date(2026, 5, 14)


def test_custom_summary_uses_calendar_year_groups_and_full_gap_without_reports():
    db = build_session()
    user, _ = create_user_and_plan(db)
    start_date = date(2024, 7, 1)
    end_date = date(2026, 7, 1)

    summary = CustomReportService(db).build_summary(user.id, start_date, end_date)

    assert summary.aggregation == "yearly"
    assert summary.longest_gap_days == summary.period_days
    assert len(summary.timeline) == 3
    assert summary.timeline[0].start_date == date(2024, 7, 1)
    assert summary.timeline[0].end_date == date(2024, 12, 31)
    assert summary.timeline[-1].end_date == date(2026, 7, 1)


def test_custom_summary_filters_by_patient_and_includes_period_boundaries():
    db = build_session()
    user, plan = create_user_and_plan(db)
    other_user, other_plan = create_user_and_plan(db, email="outro@example.com")
    end_date = date.today()
    start_date = end_date - timedelta(days=29)

    for report_date in (start_date, end_date):
        create_report(
            db,
            user=user,
            plan=plan,
            report_date=report_date,
            completed=True,
            had_symptoms=False,
        )
    create_report(
        db,
        user=user,
        plan=plan,
        report_date=start_date - timedelta(days=1),
        completed=True,
        had_symptoms=True,
        symptom_description="Fora do período",
    )
    create_report(
        db,
        user=other_user,
        plan=other_plan,
        report_date=start_date,
        completed=True,
        had_symptoms=True,
        symptom_description="Outro paciente",
    )

    summary = CustomReportService(db).build_summary(user.id, start_date, end_date)

    assert summary.metrics.total_checkins == 2
    assert summary.metrics.checkins_with_symptoms == 0
    assert summary.symptoms == []
