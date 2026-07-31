from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.models.schemas import CustomAiReportCreateRequest, CustomAiReportPreviewRequest


def build_period(days: int) -> tuple[date, date]:
    end_date = date.today()
    return end_date - timedelta(days=days - 1), end_date


def test_custom_ai_report_accepts_exactly_thirty_days():
    start_date, end_date = build_period(30)

    payload = CustomAiReportPreviewRequest(start_date=start_date, end_date=end_date)

    assert payload.start_date == start_date
    assert payload.end_date == end_date
    assert payload.modo == "avaliacao_clinica"


def test_custom_ai_report_rejects_period_shorter_than_thirty_days():
    start_date, end_date = build_period(29)

    with pytest.raises(ValidationError, match="at least 30 days"):
        CustomAiReportPreviewRequest(start_date=start_date, end_date=end_date)


def test_custom_ai_report_rejects_reversed_period():
    today = date.today()

    with pytest.raises(ValidationError, match="end_date must be greater"):
        CustomAiReportPreviewRequest(start_date=today, end_date=today - timedelta(days=30))


def test_custom_ai_report_rejects_future_end_date():
    end_date = date.today() + timedelta(days=1)

    with pytest.raises(ValidationError, match="cannot be in the future"):
        CustomAiReportPreviewRequest(start_date=end_date - timedelta(days=29), end_date=end_date)


def test_custom_ai_report_rejects_more_than_five_calendar_years():
    end_date = date.today()
    start_date = end_date.replace(year=end_date.year - 5) - timedelta(days=1)

    with pytest.raises(ValidationError, match="cannot exceed 5 calendar years"):
        CustomAiReportPreviewRequest(start_date=start_date, end_date=end_date)


def test_custom_ai_report_requires_preview_token_for_confirmation():
    start_date, end_date = build_period(30)

    with pytest.raises(ValidationError, match="at least 1 character"):
        CustomAiReportCreateRequest(
            start_date=start_date,
            end_date=end_date,
            preview_token="",
        )
