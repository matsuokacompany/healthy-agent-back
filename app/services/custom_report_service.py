from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import DailyReport
from app.models.schemas import (
    CustomAiReportPeriod,
    CustomClinicalPeriodMetrics,
    CustomClinicalSummary,
    CustomClinicalSymptomOccurrence,
    CustomClinicalTimelineGroup,
)


class CustomReportService:
    MINIMUM_COMPLETED_CHECKINS = 10
    TREND_THRESHOLD_PERCENTAGE_POINTS = 5.0

    def __init__(self, db: Session):
        self.db = db

    def build_summary(self, patient_id: int, start_date: date, end_date: date) -> CustomClinicalSummary:
        period = CustomAiReportPeriod(start_date=start_date, end_date=end_date)
        start_date = period.start_date
        end_date = period.end_date

        reports = (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == patient_id)
            .filter(DailyReport.report_date >= start_date)
            .filter(DailyReport.report_date <= end_date)
            .order_by(DailyReport.report_date.asc(), DailyReport.id.asc())
            .all()
        )
        period_days = (end_date - start_date).days + 1
        completed_checkins = sum(report.completed for report in reports)

        return CustomClinicalSummary(
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
            period_days=period_days,
            aggregation=self._aggregation_for(period_days),
            minimum_completed_checkins=self.MINIMUM_COMPLETED_CHECKINS,
            sufficient_data=completed_checkins >= self.MINIMUM_COMPLETED_CHECKINS,
            metrics=self._build_metrics(reports, period_days),
            symptom_trend=self._build_symptom_trend(reports, start_date, end_date),
            longest_gap_days=self._longest_gap_days(reports, start_date, end_date),
            symptoms=self._build_symptoms(reports),
            timeline=self._build_timeline(reports, start_date, end_date),
        )

    @staticmethod
    def _build_metrics(reports: list[DailyReport], period_days: int) -> CustomClinicalPeriodMetrics:
        completed = [report for report in reports if report.completed]
        with_symptoms = [report for report in completed if report.had_symptoms is True]
        without_symptoms = [report for report in completed if report.had_symptoms is False]
        days_with_checkins = len({report.report_date for report in reports})

        return CustomClinicalPeriodMetrics(
            total_checkins=len(reports),
            completed_checkins=len(completed),
            pending_checkins=len(reports) - len(completed),
            checkins_with_symptoms=len(with_symptoms),
            checkins_without_symptoms=len(without_symptoms),
            days_with_checkins=days_with_checkins,
            adherence_percentage=CustomReportService._percentage(len(completed), len(reports)),
            symptom_rate_percentage=CustomReportService._percentage(len(with_symptoms), len(completed)),
            calendar_coverage_percentage=CustomReportService._percentage(days_with_checkins, period_days),
        )

    @staticmethod
    def _build_symptoms(reports: list[DailyReport]) -> list[CustomClinicalSymptomOccurrence]:
        occurrences: dict[str, list[DailyReport]] = defaultdict(list)
        labels: dict[str, str] = {}
        for report in reports:
            if not report.completed or report.had_symptoms is not True or not report.symptom_description:
                continue
            description = " ".join(report.symptom_description.split())
            normalized = description.casefold()
            labels.setdefault(normalized, description)
            occurrences[normalized].append(report)

        symptoms = [
            CustomClinicalSymptomOccurrence(
                description=labels[normalized],
                occurrences=len(symptom_reports),
                first_reported_at=min(report.report_date for report in symptom_reports),
                last_reported_at=max(report.report_date for report in symptom_reports),
            )
            for normalized, symptom_reports in occurrences.items()
        ]
        return sorted(symptoms, key=lambda item: (-item.occurrences, item.description.casefold()))

    def _build_timeline(
        self,
        reports: list[DailyReport],
        start_date: date,
        end_date: date,
    ) -> list[CustomClinicalTimelineGroup]:
        aggregation = self._aggregation_for((end_date - start_date).days + 1)
        groups = []
        group_start = start_date
        while group_start <= end_date:
            group_end = min(self._next_group_start(group_start, aggregation) - timedelta(days=1), end_date)
            group_reports = [report for report in reports if group_start <= report.report_date <= group_end]
            groups.append(
                CustomClinicalTimelineGroup(
                    start_date=group_start,
                    end_date=group_end,
                    metrics=self._build_metrics(group_reports, (group_end - group_start).days + 1),
                )
            )
            group_start = group_end + timedelta(days=1)
        return groups

    def _build_symptom_trend(self, reports: list[DailyReport], start_date: date, end_date: date) -> str:
        if sum(report.completed for report in reports) < self.MINIMUM_COMPLETED_CHECKINS:
            return "insufficient_data"
        midpoint = start_date + timedelta(days=((end_date - start_date).days + 1) // 2)
        first_half = [report for report in reports if report.report_date < midpoint]
        second_half = [report for report in reports if report.report_date >= midpoint]
        first_rate = self._completed_symptom_rate(first_half)
        second_rate = self._completed_symptom_rate(second_half)
        if first_rate is None or second_rate is None:
            return "insufficient_data"

        difference = second_rate - first_rate
        if difference >= self.TREND_THRESHOLD_PERCENTAGE_POINTS:
            return "increasing"
        if difference <= -self.TREND_THRESHOLD_PERCENTAGE_POINTS:
            return "decreasing"
        return "stable"

    @staticmethod
    def _completed_symptom_rate(reports: list[DailyReport]) -> float | None:
        completed = [report for report in reports if report.completed]
        if not completed:
            return None
        with_symptoms = sum(report.had_symptoms is True for report in completed)
        return CustomReportService._percentage(with_symptoms, len(completed))

    @staticmethod
    def _longest_gap_days(reports: list[DailyReport], start_date: date, end_date: date) -> int:
        report_dates = sorted({report.report_date for report in reports})
        if not report_dates:
            return (end_date - start_date).days + 1

        longest_gap = (report_dates[0] - start_date).days
        for previous_date, current_date in zip(report_dates, report_dates[1:]):
            longest_gap = max(longest_gap, (current_date - previous_date).days - 1)
        return max(longest_gap, (end_date - report_dates[-1]).days)

    @staticmethod
    def _aggregation_for(period_days: int) -> str:
        if period_days <= 90:
            return "weekly"
        if period_days <= 365:
            return "monthly"
        return "yearly"

    @staticmethod
    def _next_group_start(group_start: date, aggregation: str) -> date:
        if aggregation == "weekly":
            return group_start + timedelta(days=7)
        if aggregation == "monthly":
            if group_start.month == 12:
                return group_start.replace(year=group_start.year + 1, month=1, day=1)
            return group_start.replace(month=group_start.month + 1, day=1)
        return group_start.replace(year=group_start.year + 1, month=1, day=1)

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        return round((numerator / denominator * 100), 1) if denominator else 0.0
