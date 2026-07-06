from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

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
    AnamneseRead,
    PatientDashboardCheckinsResponse,
    PatientDashboardResponseV2,
    ProfessionalAiReportResponse,
    ProfessionalPatientRead,
)
from app.core.permissions import is_admin, require_role
from app.services.insight_service import InsightService
from app.services.patient_dashboard_service import PaginationParams, PatientDashboardService, ReportFilters
from app.services.report_service import ReportService


class ProfessionalService:
    """Read-only professional workspace operations scoped to monitored patients."""

    def __init__(self, db: Session):
        self.db = db
        self.dashboard_service = PatientDashboardService(db)

    def list_patients(self, current_user: User) -> list[ProfessionalPatientRead]:
        profile = self._get_access_profile(current_user)
        query = (
            self.db.query(MonitoringPlan)
            .options(selectinload(MonitoringPlan.patient))
            .filter(MonitoringPlan.active.is_(True))
        )
        if profile:
            query = query.join(MonitoringProfessional).filter(
                MonitoringProfessional.professional_profile_id == profile.id,
                MonitoringProfessional.active.is_(True),
            )
        plans = query.order_by(MonitoringPlan.created_at.desc(), MonitoringPlan.id.desc()).all()

        patient_items: dict[int, ProfessionalPatientRead] = {}
        for plan in plans:
            if not plan.patient:
                continue
            last_report = self._get_last_report(plan.patient_id, plan.id)
            symptoms_count = self._count_symptom_reports(plan.patient_id, plan.id)
            existing = patient_items.get(plan.patient_id)
            item = ProfessionalPatientRead(
                patient_id=plan.patient_id,
                name=plan.patient.name,
                email=plan.patient.email,
                phone=plan.patient.phone,
                monitoring_plan_id=plan.id,
                plan_title=plan.title,
                active=plan.active,
                start_date=plan.start_date,
                end_date=plan.end_date,
                last_checkin_at=last_report.updated_at if last_report else None,
                last_status=last_report.status if last_report else None,
                symptom_reports_count=symptoms_count,
            )
            if existing is None or (item.last_checkin_at or datetime.min.replace(tzinfo=timezone.utc)) > (
                existing.last_checkin_at or datetime.min.replace(tzinfo=timezone.utc)
            ):
                patient_items[plan.patient_id] = item
        return list(patient_items.values())

    def get_dashboard(self, current_user: User, patient_id: int) -> PatientDashboardResponseV2:
        patient = self._require_patient_access(current_user, patient_id)
        return self._build_patient_dashboard(patient)

    def get_checkins(
        self,
        current_user: User,
        patient_id: int,
        *,
        pagination: PaginationParams,
        filters: ReportFilters,
        order: str,
    ) -> PatientDashboardCheckinsResponse:
        self._require_patient_access(current_user, patient_id)
        if filters.start_date and filters.end_date and filters.end_date < filters.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be greater than or equal to start_date",
            )
        query = self.dashboard_service._reports_query(patient_id, filters)
        total = query.count()
        items = (
            self.dashboard_service._apply_order(query, order)
            .offset(pagination.offset)
            .limit(pagination.per_page)
            .all()
        )
        return PatientDashboardCheckinsResponse(
            items=[self.dashboard_service._build_report_item(report) for report in items],
            pagination=self.dashboard_service._build_pagination(pagination, total),
        )

    def get_anamnese(self, current_user: User, patient_id: int) -> AnamneseRead:
        self._require_patient_access(current_user, patient_id)
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if not anamnese:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anamnese not found")
        return anamnese

    def generate_ai_report(
        self,
        current_user: User,
        patient_id: int,
        *,
        periodo: Literal["diario", "semanal", "mensal"],
        modo: Literal["preventivo", "avaliacao_clinica"],
        api_key: str | None,
    ) -> ProfessionalAiReportResponse:
        self._require_patient_access(current_user, patient_id)
        clinical_summary = self._build_clinical_summary(patient_id, periodo)
        ai = InsightService(api_key=api_key or "", modo=modo).gerar_interpretacao(clinical_summary)
        return ProfessionalAiReportResponse(
            patient_id=patient_id,
            periodo=periodo,
            modo=modo,
            clinical_summary=clinical_summary,
            ai=ai,
        )

    def _get_access_profile(self, current_user: User) -> ProfessionalProfile | None:
        if is_admin(current_user):
            return None
        require_role(current_user, RoleNameEnum.PROFESSIONAL)
        profile = (
            self.db.query(ProfessionalProfile)
            .filter(ProfessionalProfile.user_id == current_user.id, ProfessionalProfile.active.is_(True))
            .first()
        )
        if not profile:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active professional profile required")
        return profile

    def _require_patient_access(self, current_user: User, patient_id: int) -> User:
        patient = self.db.query(User).filter(User.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        if is_admin(current_user):
            return patient
        profile = self._get_access_profile(current_user)
        exists = (
            self.db.query(MonitoringProfessional)
            .join(MonitoringPlan, MonitoringPlan.id == MonitoringProfessional.monitoring_plan_id)
            .filter(
                MonitoringPlan.patient_id == patient_id,
                MonitoringPlan.active.is_(True),
                MonitoringProfessional.professional_profile_id == profile.id,
                MonitoringProfessional.active.is_(True),
            )
            .first()
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this patient")
        return patient

    def _build_patient_dashboard(self, patient: User) -> PatientDashboardResponseV2:
        today = datetime.now(self.dashboard_service.timezone).date()
        active_plan = self.dashboard_service._get_active_plan(patient.id, today)
        active_plan_id = active_plan.id if active_plan else None
        today_report = (
            self.dashboard_service._get_today_report(patient.id, today, active_plan_id)
            if active_plan_id
            else None
        )
        statistics = (
            self.dashboard_service._get_statistics(patient.id, ReportFilters(), active_plan_id)
            if active_plan_id
            else self.dashboard_service._get_statistics(patient.id, ReportFilters())
        )
        anamnese = self.dashboard_service._get_anamnese(patient.id)
        monitoring = self.dashboard_service._build_monitoring(active_plan, today)
        today_summary = self.dashboard_service._build_today(today_report)
        return PatientDashboardResponseV2(
            user=self.dashboard_service._build_user(patient),
            monitoring=monitoring,
            today=today_summary,
            next_checkin=self.dashboard_service._build_next_checkin(active_plan),
            anamnesis_summary=self.dashboard_service._build_anamnesis_summary(anamnese),
            statistics=statistics,
            last_response=self.dashboard_service._get_last_response(patient.id, active_plan_id) if active_plan_id else None,
            professionals=self.dashboard_service._build_professionals(active_plan),
            alerts=self.dashboard_service._build_alerts(monitoring, today_summary, anamnese),
        )

    def _build_clinical_summary(self, patient_id: int, periodo: str) -> str:
        report_text = ReportService(self.db).gerar_relatorio(patient_id, periodo)
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if not anamnese:
            anamnese_text = "Anamnese não registrada."
        else:
            anamnese_text = anamnese.info
        return "\n\n".join([
            "ANAMNESE DO PACIENTE:",
            anamnese_text,
            "RELATÓRIO DE SINTOMAS E CHECK-INS:",
            report_text,
        ])

    def _get_last_report(self, patient_id: int, monitoring_plan_id: int) -> DailyReport | None:
        return (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == patient_id, DailyReport.monitoring_plan_id == monitoring_plan_id)
            .order_by(DailyReport.updated_at.desc(), DailyReport.id.desc())
            .first()
        )

    def _count_symptom_reports(self, patient_id: int, monitoring_plan_id: int) -> int:
        since = datetime.now(timezone.utc) - timedelta(days=30)
        return int(
            self.db.query(func.count(DailyReport.id))
            .filter(
                DailyReport.user_id == patient_id,
                DailyReport.monitoring_plan_id == monitoring_plan_id,
                DailyReport.completed.is_(True),
                DailyReport.had_symptoms.is_(True),
                DailyReport.updated_at >= since,
            )
            .scalar()
            or 0
        )
