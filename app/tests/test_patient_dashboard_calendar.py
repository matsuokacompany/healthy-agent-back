from datetime import date, datetime, timezone

from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum
from app.services.patient_dashboard_service import PatientDashboardService


def build_report(*, diet_adherence=None, medication_adherence=None, had_symptoms=None, completed=True):
    now = datetime.now(timezone.utc)
    return DailyReport(
        id=1,
        user_id=1,
        monitoring_plan_id=1,
        report_date=date.today(),
        check_type=CheckTypeEnum.MORNING,
        status=DailyReportStatusEnum.COMPLETED,
        completed=completed,
        had_symptoms=had_symptoms,
        diet_adherence=diet_adherence,
        medication_adherence=medication_adherence,
        prompt_sent_at=now,
        expires_at=now,
        updated_at=now,
    )


def test_calendar_day_flags_diet_followed_and_medication_taken():
    report = build_report(diet_adherence=True, medication_adherence=True)

    day = PatientDashboardService(db=None)._build_calendar_day(date.today(), [report])

    assert day.diet_followed is True
    assert day.medication_taken is True


def test_calendar_day_does_not_flag_when_answered_no():
    report = build_report(diet_adherence=False, medication_adherence=False)

    day = PatientDashboardService(db=None)._build_calendar_day(date.today(), [report])

    assert day.diet_followed is False
    assert day.medication_taken is False


def test_calendar_day_does_not_flag_when_unanswered():
    report = build_report(diet_adherence=None, medication_adherence=None, completed=False)

    day = PatientDashboardService(db=None)._build_calendar_day(date.today(), [report])

    assert day.diet_followed is False
    assert day.medication_taken is False


def test_calendar_checkin_exposes_diet_and_medication_adherence():
    report = build_report(diet_adherence=True, medication_adherence=False)

    day = PatientDashboardService(db=None)._build_calendar_day(date.today(), [report])

    assert day.checkins[0].diet_adherence is True
    assert day.checkins[0].medication_adherence is False
