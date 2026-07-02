from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Integer, func
from sqlalchemy.orm import Query, Session, selectinload

from app.core.config import settings
from app.core.permissions import has_any_role, require_role
from app.models.models import (
    Anamnese,
    DailyReport,
    DailyReportStatusEnum as ModelDailyReportStatusEnum,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    RoleNameEnum,
    User,
)
from app.models.schemas import (
    PatientAnamnesisSummary,
    PatientDashboardAlert,
    PatientDashboardCalendarCheckin,
    PatientDashboardCalendarDay,
    PatientDashboardCalendarResponse,
    PatientDashboardCheckinsResponse,
    PatientDashboardHistoryResponse,
    PatientDashboardPagination,
    PatientDashboardReportItem,
    PatientDashboardResponseV2,
    PatientDashboardStatistics,
    PatientDashboardStatisticsResponse,
    PatientLastResponse,
    PatientDashboardToday,
    PatientDashboardUser,
    PatientMonitoringSummary,
    PatientNextCheckin,
    PatientResponsibleProfessional,
)


@dataclass(frozen=True)
class ReportFilters:
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = None
    had_symptoms: bool | None = None


@dataclass(frozen=True)
class PaginationParams:
    page: int = 1
    per_page: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class PatientDashboardService:
    """Aggregates existing patient data for patient dashboard endpoints."""

    MAX_ANAMNESIS_PREVIEW_ITEMS = 3
    PERIOD_DAYS = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "1y": 365,
    }

    def __init__(self, db: Session):
        self.db = db
        self.timezone = ZoneInfo(settings.SCHEDULER_TIMEZONE)

    def get_dashboard(self, current_user: User) -> PatientDashboardResponseV2:
        self._ensure_patient_only(current_user)

        today = datetime.now(self.timezone).date()
        active_plan = self._get_active_plan(current_user.id, today)
        active_plan_id = active_plan.id if active_plan else None
        today_report = (
            self._get_today_report(current_user.id, today, active_plan_id)
            if active_plan_id
            else None
        )
        statistics = (
            self._get_statistics(current_user.id, ReportFilters(), active_plan_id)
            if active_plan_id
            else PatientDashboardStatistics.empty()
        )
        last_response = self._get_last_response(current_user.id, active_plan_id) if active_plan_id else None
        anamnese = self._get_anamnese(current_user.id)
        monitoring = self._build_monitoring(active_plan, today)
        today_summary = self._build_today(today_report)

        return PatientDashboardResponseV2(
            user=self._build_user(current_user),
            monitoring=monitoring,
            today=today_summary,
            next_checkin=self._build_next_checkin(active_plan),
            anamnesis_summary=self._build_anamnesis_summary(anamnese),
            statistics=statistics,
            last_response=last_response,
            professionals=self._build_professionals(active_plan),
            alerts=self._build_alerts(monitoring, today_summary, anamnese),
        )

    def get_history(
        self,
        current_user: User,
        *,
        pagination: PaginationParams,
        filters: ReportFilters,
        order: str,
    ) -> PatientDashboardHistoryResponse:
        self._ensure_patient_only(current_user)
        query = self._reports_query(current_user.id, filters)
        total = query.count()
        items = (
            self._apply_order(query, order)
            .offset(pagination.offset)
            .limit(pagination.per_page)
            .all()
        )
        return PatientDashboardHistoryResponse(
            items=[self._build_report_item(report) for report in items],
            pagination=self._build_pagination(pagination, total),
        )

    def get_checkins(
        self,
        current_user: User,
        *,
        pagination: PaginationParams,
        filters: ReportFilters,
        order: str,
    ) -> PatientDashboardCheckinsResponse:
        self._ensure_patient_only(current_user)
        query = self._reports_query(current_user.id, filters)
        total = query.count()
        items = (
            self._apply_order(query, order)
            .offset(pagination.offset)
            .limit(pagination.per_page)
            .all()
        )
        return PatientDashboardCheckinsResponse(
            items=[self._build_report_item(report) for report in items],
            pagination=self._build_pagination(pagination, total),
        )

    def get_calendar(self, current_user: User, *, year: int, month: int) -> PatientDashboardCalendarResponse:
        self._ensure_patient_only(current_user)
        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        reports = (
            self._reports_query(current_user.id, ReportFilters(start_date=start_date, end_date=end_date))
            .order_by(DailyReport.report_date.asc(), DailyReport.prompt_sent_at.asc(), DailyReport.id.asc())
            .all()
        )

        reports_by_day: dict[date, list[DailyReport]] = {}
        for report in reports:
            reports_by_day.setdefault(report.report_date, []).append(report)

        days = []
        for day in range(1, last_day + 1):
            current_date = date(year, month, day)
            day_reports = reports_by_day.get(current_date, [])
            days.append(self._build_calendar_day(current_date, day_reports))

        return PatientDashboardCalendarResponse(year=year, month=month, days=days)

    def get_statistics(
        self,
        current_user: User,
        *,
        period: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> PatientDashboardStatisticsResponse:
        self._ensure_patient_only(current_user)
        filters = self._build_period_filters(period=period, start_date=start_date, end_date=end_date)
        return PatientDashboardStatisticsResponse(
            period=period,
            start_date=filters.start_date,
            end_date=filters.end_date,
            statistics=self._get_statistics(current_user.id, filters),
        )

    @staticmethod
    def _ensure_patient_only(current_user: User) -> None:
        require_role(current_user, RoleNameEnum.PATIENT)
        if has_any_role(current_user, {RoleNameEnum.ADMIN, RoleNameEnum.SUPER_ADMIN, RoleNameEnum.PROFESSIONAL}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patient dashboard is only available for patient users",
            )

    @staticmethod
    def _build_user(user: User) -> PatientDashboardUser:
        first_name = user.name.split()[0] if user.name and user.name.split() else user.name
        return PatientDashboardUser(id=user.id, name=user.name, first_name=first_name, avatar=None)

    def _get_active_plan(self, patient_id: int, today: date) -> MonitoringPlan | None:
        return (
            self.db.query(MonitoringPlan)
            .options(
                selectinload(MonitoringPlan.professional_links)
                .joinedload(MonitoringProfessional.professional)
                .joinedload(ProfessionalProfile.user)
            )
            .filter(MonitoringPlan.patient_id == patient_id)
            .filter(MonitoringPlan.active.is_(True))
            .filter((MonitoringPlan.start_date.is_(None)) | (MonitoringPlan.start_date <= today))
            .filter((MonitoringPlan.end_date.is_(None)) | (MonitoringPlan.end_date >= today))
            .order_by(MonitoringPlan.start_date.desc().nullslast(), MonitoringPlan.id.desc())
            .first()
        )

    @staticmethod
    def _build_monitoring(plan: MonitoringPlan | None, today: date) -> PatientMonitoringSummary:
        if not plan:
            return PatientMonitoringSummary(active=False)

        days_active = max((today - plan.start_date).days, 0) if plan.start_date else None
        days_remaining = max((plan.end_date - today).days, 0) if plan.end_date else None
        return PatientMonitoringSummary(
            id=plan.id,
            active=True,
            title=plan.title,
            start_date=plan.start_date,
            end_date=plan.end_date,
            days_active=days_active,
            days_remaining=days_remaining,
        )

    def _get_today_report(self, user_id: int, today: date, monitoring_plan_id: int | None) -> DailyReport | None:
        query = self.db.query(DailyReport).filter(DailyReport.user_id == user_id, DailyReport.report_date == today)
        if monitoring_plan_id is not None:
            query = query.filter(DailyReport.monitoring_plan_id == monitoring_plan_id)
        return query.order_by(DailyReport.prompt_sent_at.desc(), DailyReport.id.desc()).first()

    @staticmethod
    def _build_today(report: DailyReport | None) -> PatientDashboardToday:
        if not report:
            return PatientDashboardToday(has_checkin=False)
        return PatientDashboardToday(
            has_checkin=True,
            completed=report.completed,
            status=report.status,
            prompt_sent_at=report.prompt_sent_at,
            answered_at=report.updated_at if report.completed else None,
        )

    def _reports_query(self, user_id: int, filters: ReportFilters) -> Query:
        query = self.db.query(DailyReport).filter(DailyReport.user_id == user_id)
        if filters.start_date:
            query = query.filter(DailyReport.report_date >= filters.start_date)
        if filters.end_date:
            query = query.filter(DailyReport.report_date <= filters.end_date)
        if filters.status:
            query = query.filter(DailyReport.status == ModelDailyReportStatusEnum(filters.status))
        if filters.had_symptoms is not None:
            query = query.filter(DailyReport.had_symptoms.is_(filters.had_symptoms))
        return query

    @staticmethod
    def _apply_order(query: Query, order: str) -> Query:
        if order == "asc":
            return query.order_by(DailyReport.report_date.asc(), DailyReport.prompt_sent_at.asc(), DailyReport.id.asc())
        return query.order_by(DailyReport.report_date.desc(), DailyReport.prompt_sent_at.desc(), DailyReport.id.desc())

    def _get_statistics(
        self,
        user_id: int,
        filters: ReportFilters,
        monitoring_plan_id: int | None = None,
    ) -> PatientDashboardStatistics:
        query = self.db.query(
            func.count(DailyReport.id).label("total"),
            func.sum(DailyReport.completed.cast(Integer)).label("answered"),
            func.sum(
                ((DailyReport.completed.is_(True)) & (DailyReport.had_symptoms.is_(True))).cast(Integer)
            ).label("with_symptoms"),
            func.sum(
                ((DailyReport.completed.is_(True)) & (DailyReport.had_symptoms.is_(False))).cast(Integer)
            ).label("without_symptoms"),
        ).filter(DailyReport.user_id == user_id)
        if monitoring_plan_id is not None:
            query = query.filter(DailyReport.monitoring_plan_id == monitoring_plan_id)
        if filters.start_date:
            query = query.filter(DailyReport.report_date >= filters.start_date)
        if filters.end_date:
            query = query.filter(DailyReport.report_date <= filters.end_date)
        if filters.status:
            query = query.filter(DailyReport.status == ModelDailyReportStatusEnum(filters.status))
        if filters.had_symptoms is not None:
            query = query.filter(DailyReport.had_symptoms.is_(filters.had_symptoms))

        row = query.one()
        total = int(row.total or 0)
        answered = int(row.answered or 0)
        with_symptoms = int(row.with_symptoms or 0)
        without_symptoms = int(row.without_symptoms or 0)
        missed = max(total - answered, 0)
        adherence = round((answered / total) * 100, 1) if total else 0.0
        return PatientDashboardStatistics(
            total=total,
            answered=answered,
            missed=missed,
            with_symptoms=with_symptoms,
            without_symptoms=without_symptoms,
            adherence=adherence,
        )

    def _get_last_response(self, user_id: int, monitoring_plan_id: int | None = None) -> PatientLastResponse | None:
        query = self.db.query(DailyReport).filter(
            DailyReport.user_id == user_id,
            DailyReport.completed.is_(True),
        )
        if monitoring_plan_id is not None:
            query = query.filter(DailyReport.monitoring_plan_id == monitoring_plan_id)

        report = query.order_by(DailyReport.updated_at.desc(), DailyReport.id.desc()).first()
        if not report:
            return None
        return PatientLastResponse(
            date=report.report_date,
            status=report.status,
            had_symptoms=report.had_symptoms,
        )

    def _build_period_filters(self, *, period: str | None, start_date: date | None, end_date: date | None) -> ReportFilters:
        if period and (start_date or end_date):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use period or custom date range, not both",
            )
        today = datetime.now(self.timezone).date()
        if period:
            days = self.PERIOD_DAYS.get(period)
            if not days:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid period. Use: 7d, 30d, 90d, 1y",
                )
            return ReportFilters(start_date=today - timedelta(days=days - 1), end_date=today)
        if start_date and end_date and end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be greater than or equal to start_date",
            )
        return ReportFilters(start_date=start_date, end_date=end_date)

    @staticmethod
    def _build_report_item(report: DailyReport) -> PatientDashboardReportItem:
        return PatientDashboardReportItem(
            id=report.id,
            monitoring_plan_id=report.monitoring_plan_id,
            report_date=report.report_date,
            check_type=report.check_type,
            status=report.status,
            completed=report.completed,
            had_symptoms=report.had_symptoms,
            symptom_description=report.symptom_description,
            suspected_cause=report.suspected_cause,
            prompt_sent_at=report.prompt_sent_at,
            answered_at=report.updated_at if report.completed else None,
            expires_at=report.expires_at,
        )

    @staticmethod
    def _build_pagination(pagination: PaginationParams, total: int) -> PatientDashboardPagination:
        total_pages = ceil(total / pagination.per_page) if total else 0
        return PatientDashboardPagination(
            page=pagination.page,
            per_page=pagination.per_page,
            total=total,
            total_pages=total_pages,
        )

    def _build_calendar_day(self, current_date: date, reports: list[DailyReport]) -> PatientDashboardCalendarDay:
        checkins = [
            PatientDashboardCalendarCheckin(
                id=report.id,
                check_type=report.check_type,
                status=report.status,
                completed=report.completed,
                had_symptoms=report.had_symptoms,
                prompt_sent_at=report.prompt_sent_at,
                answered_at=report.updated_at if report.completed else None,
            )
            for report in reports
        ]
        return PatientDashboardCalendarDay(
            date=current_date,
            has_checkin=bool(reports),
            completed=bool(reports) and all(report.completed for report in reports),
            pending=any(not report.completed for report in reports),
            has_symptoms=any(report.had_symptoms is True for report in reports),
            statuses=[report.status for report in reports],
            checkins=checkins,
        )

    def _build_next_checkin(self, plan: MonitoringPlan | None) -> PatientNextCheckin | None:
        if not plan or not plan.active:
            return None
        now = datetime.now(self.timezone)
        scheduled_time = time(settings.SCHEDULER_MORNING_HOUR, settings.SCHEDULER_MORNING_MINUTE)
        scheduled_at = datetime.combine(now.date(), scheduled_time, tzinfo=self.timezone)
        if scheduled_at <= now:
            scheduled_at += timedelta(days=1)
        if plan.end_date and scheduled_at.date() > plan.end_date:
            return None
        return PatientNextCheckin(scheduled_at=scheduled_at)

    @staticmethod
    def _build_professionals(plan: MonitoringPlan | None) -> list[PatientResponsibleProfessional]:
        if not plan:
            return []
        professionals = []
        for link in plan.professional_links:
            if not link.active or not link.professional or not link.professional.user:
                continue
            professionals.append(
                PatientResponsibleProfessional(
                    id=link.professional.id,
                    name=link.professional.user.name,
                    specialty=link.professional.specialty,
                )
            )
        return professionals

    def _get_anamnese(self, user_id: int) -> Anamnese | None:
        return self.db.query(Anamnese).filter(Anamnese.user_id == user_id).first()

    def _build_anamnesis_summary(self, anamnese: Anamnese | None) -> PatientAnamnesisSummary:
        if not anamnese:
            return PatientAnamnesisSummary(has_anamnesis=False)
        preview = self._extract_anamnesis_preview(anamnese.info)
        if not preview:
            return PatientAnamnesisSummary(has_anamnesis=True)
        return PatientAnamnesisSummary(
            has_anamnesis=True,
            conditions_count=len(preview),
            preview=preview[: self.MAX_ANAMNESIS_PREVIEW_ITEMS],
        )

    @staticmethod
    def _extract_anamnesis_preview(info: str) -> list[str]:
        separators = ["\n", ";", ","]
        fragments = [info]
        for separator in separators:
            next_fragments = []
            for fragment in fragments:
                next_fragments.extend(fragment.split(separator))
            fragments = next_fragments

        cleaned = []
        for fragment in fragments:
            item = fragment.strip().strip("-•*0123456789. )(")
            if 2 <= len(item) <= 80:
                cleaned.append(item)
        return cleaned

    @staticmethod
    def _build_alerts(
        monitoring: PatientMonitoringSummary,
        today: PatientDashboardToday,
        anamnese: Anamnese | None,
    ) -> list[PatientDashboardAlert]:
        alerts = []
        if not monitoring.active:
            alerts.append(
                PatientDashboardAlert(
                    type="monitoring",
                    severity="warning",
                    message="Nenhum plano de monitoramento ativo.",
                )
            )
        if today.has_checkin and not today.completed:
            alerts.append(
                PatientDashboardAlert(
                    type="checkin",
                    severity="warning",
                    message="Você possui um check-in pendente hoje.",
                )
            )
        if not anamnese:
            alerts.append(
                PatientDashboardAlert(
                    type="anamnesis",
                    severity="info",
                    message="Complete sua anamnese para melhorar o acompanhamento.",
                )
            )
        return alerts
