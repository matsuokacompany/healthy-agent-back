from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.permissions import has_any_role, require_role
from app.models.models import (
    Anamnese,
    DailyReport,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    RoleNameEnum,
    User,
)
from app.models.schemas import (
    PatientAnamnesisSummary,
    PatientDashboardResponse,
    PatientDashboardStatistics,
    PatientDashboardToday,
    PatientDashboardUser,
    PatientLastResponse,
    PatientMonitoringSummary,
    PatientNextCheckin,
    PatientResponsibleProfessional,
)


class PatientDashboardService:
    """Aggregates existing patient data for the patient dashboard."""

    MAX_ANAMNESIS_PREVIEW_ITEMS = 3

    def __init__(self, db: Session):
        self.db = db
        self.timezone = ZoneInfo(settings.SCHEDULER_TIMEZONE)

    def get_dashboard(self, current_user: User) -> PatientDashboardResponse:
        self._ensure_patient_only(current_user)

        today = datetime.now(self.timezone).date()
        active_plan = self._get_active_plan(current_user.id, today)
        reports_scope_plan_id = active_plan.id if active_plan else None

        today_report = (
            self._get_today_report(current_user.id, today, reports_scope_plan_id)
            if reports_scope_plan_id
            else None
        )
        statistics = (
            self._get_statistics(current_user.id, reports_scope_plan_id)
            if reports_scope_plan_id
            else PatientDashboardStatistics.empty()
        )
        last_response = (
            self._get_last_response(current_user.id, reports_scope_plan_id)
            if reports_scope_plan_id
            else None
        )
        anamnese = self._get_anamnese(current_user.id)

        return PatientDashboardResponse(
            user=self._build_user(current_user),
            monitoring=self._build_monitoring(active_plan, today),
            today=self._build_today(today_report),
            statistics=statistics,
            last_response=last_response,
            next_checkin=self._build_next_checkin(active_plan),
            professionals=self._build_professionals(active_plan),
            anamnesis_summary=self._build_anamnesis_summary(anamnese),
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
        return PatientDashboardUser(
            id=user.id,
            name=user.name,
            first_name=first_name,
            avatar=None,
        )

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

        days_active = None
        if plan.start_date:
            days_active = max((today - plan.start_date).days, 0)

        days_remaining = None
        if plan.end_date:
            days_remaining = max((plan.end_date - today).days, 0)

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
        query = self.db.query(DailyReport).filter(
            DailyReport.user_id == user_id,
            DailyReport.report_date == today,
        )
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

    def _get_statistics(self, user_id: int, monitoring_plan_id: int | None) -> PatientDashboardStatistics:
        query = self.db.query(
            func.count(DailyReport.id).label("total"),
            func.sum(DailyReport.completed.cast(Integer)).label("answered"),
            func.sum(((DailyReport.completed.is_(True)) & (DailyReport.had_symptoms.is_(True))).cast(Integer)).label("with_symptoms"),
            func.sum(((DailyReport.completed.is_(True)) & (DailyReport.had_symptoms.is_(False))).cast(Integer)).label("without_symptoms"),
        ).filter(DailyReport.user_id == user_id)
        if monitoring_plan_id is not None:
            query = query.filter(DailyReport.monitoring_plan_id == monitoring_plan_id)

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

    def _get_last_response(self, user_id: int, monitoring_plan_id: int | None) -> PatientLastResponse | None:
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
