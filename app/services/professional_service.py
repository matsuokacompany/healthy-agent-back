import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.models import (
    AiReportCache,
    AiReportStatusEnum,
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
    ProfessionalPatientCreate,
    ProfessionalPatientCreateResponse,
    CustomAiReportPreviewRequest,
    CustomAiReportPreviewResponse,
    CustomAiReportCreateRequest,
    CustomAiReportResponse,
    CustomAiReportListResponse,
)
from app.core.auth import assign_role
from app.core.access_policy import AccessPolicy
from app.core.permissions import is_admin, require_role
from app.services.insight_service import InsightService
from app.services.custom_report_preview_service import CustomReportPreviewService
from app.services.custom_report_generation_service import CustomReportCostPolicy, CustomReportGenerationService
from app.services.custom_report_history_service import CustomReportHistoryService
from app.services.patient_dashboard_service import PaginationParams, PatientDashboardService, ReportFilters
from app.db.security_context import set_database_service_context
from app.services.report_service import ReportService
from app.services.anamnese_clinical_service import AnamneseClinicalService


class ProfessionalService:
    """Professional workspace operations scoped to monitored patients."""

    def __init__(self, db: Session):
        self.db = db
        self.dashboard_service = PatientDashboardService(db)

    def create_patient(
        self,
        current_user: User,
        payload: ProfessionalPatientCreate,
    ) -> ProfessionalPatientCreateResponse:
        """Create a patient, initial plan, and link them to the requesting professional."""
        profile = self._get_access_profile(current_user)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Active professional profile required",
            )
        # Provisioning must check global uniqueness and create the patient,
        # plan, role, and initial professional link atomically before a normal
        # patient access relationship exists.
        set_database_service_context(self.db, "professional_patient_provisioning")
        if self.db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        if payload.cpf and self.db.query(User).filter(User.cpf == payload.cpf).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CPF already registered")
        if payload.phone:
            normalized_phone = "".join(character for character in payload.phone if character.isdigit()) or None
            if normalized_phone and self.db.query(User).filter(User.phone == normalized_phone).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone already registered")
        else:
            normalized_phone = None
        if payload.plan_start_date and payload.plan_end_date and payload.plan_end_date < payload.plan_start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plan_end_date must be greater than or equal to plan_start_date",
            )

        patient = User(
            name=payload.name,
            email=payload.email,
            phone=normalized_phone,
            city=payload.city,
            state=payload.state,
            gender=payload.gender,
            birth_date=payload.birth_date,
            cpf=payload.cpf,
            is_admin=False,
        )
        self.db.add(patient)
        self.db.flush()
        assign_role(self.db, patient, RoleNameEnum.PATIENT)
        plan = MonitoringPlan(
            patient_id=patient.id,
            title=payload.plan_title,
            description=payload.plan_description,
            active=True,
            start_date=payload.plan_start_date,
            end_date=payload.plan_end_date,
        )
        self.db.add(plan)
        self.db.flush()
        self.db.add(
            MonitoringProfessional(
                monitoring_plan_id=plan.id,
                professional_profile_id=profile.id,
                role="responsible",
                active=True,
            )
        )
        self.db.commit()
        self.db.refresh(patient)
        self.db.refresh(plan)
        return ProfessionalPatientCreateResponse(patient=patient, monitoring_plan=plan)

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
        return AnamneseClinicalService.hydrate(anamnese)

    def create_anamnese(self, current_user: User, patient_id: int, info: str) -> Anamnese:
        self._require_patient_access(current_user, patient_id)
        if self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient already has an anamnese",
            )
        anamnese = Anamnese(user_id=patient_id, info=info)
        self.db.add(anamnese)
        try:
            self.db.flush()
            AnamneseClinicalService.write(anamnese, info)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient already has an anamnese",
            )
        self.db.refresh(anamnese)
        return anamnese

    def update_anamnese(self, current_user: User, patient_id: int, info: str) -> Anamnese:
        self._require_patient_access(current_user, patient_id)
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if not anamnese:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anamnese not found")
        AnamneseClinicalService.write(anamnese, info)
        self.db.commit()
        self.db.refresh(anamnese)
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
        self._require_report_role(current_user)
        self._require_patient_access(current_user, patient_id)
        clinical_summary = self._build_clinical_summary(patient_id, periodo)
        week_start = self._current_week_start()
        cached_report = (
            self.db.query(AiReportCache)
            .filter(AiReportCache.patient_id == patient_id)
            .filter(AiReportCache.created_at >= week_start)
            .order_by(AiReportCache.created_at.desc(), AiReportCache.id.desc())
            .first()
        )
        if cached_report:
            AiReportClinicalService.hydrate(cached_report)
            return ProfessionalAiReportResponse(
                patient_id=patient_id,
                periodo=cached_report.periodo,
                modo=cached_report.modo,
                clinical_summary=cached_report.clinical_summary,
                ai=cached_report.ai_response,
            )

        ai = InsightService(api_key=api_key or "", modo=modo).gerar_interpretacao(clinical_summary)
        generated_at = datetime.now(timezone.utc)
        report = AiReportCache(
                patient_id=patient_id,
                professional_user_id=current_user.id,
                periodo=periodo,
                modo=modo,
                clinical_summary_hash=self._hash_text(clinical_summary),
                clinical_summary=clinical_summary,
                ai_response=ai,
                status=AiReportStatusEnum.COMPLETED.value,
                generated_at=generated_at,
                next_generation_at=generated_at + timedelta(days=30),
            )
        self.db.add(report)
        self.db.flush()
        AiReportClinicalService.write_summary(report, clinical_summary)
        AiReportClinicalService.write_response(report, ai)
        self.db.commit()
        return ProfessionalAiReportResponse(
            patient_id=patient_id,
            periodo=periodo,
            modo=modo,
            clinical_summary=clinical_summary,
            ai=ai,
        )

    def preview_custom_ai_report(
        self,
        current_user: User,
        patient_id: int,
        *,
        payload: CustomAiReportPreviewRequest,
        token_secret: str | None,
    ) -> CustomAiReportPreviewResponse:
        self._require_report_role(current_user)
        self._require_patient_access(current_user, patient_id)
        if not token_secret or len(token_secret) < CustomReportPreviewService.MINIMUM_TOKEN_SECRET_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI report preview is not configured",
            )
        return CustomReportPreviewService(self.db, token_secret).preview(
            patient_id=patient_id,
            requested_by_user_id=current_user.id,
            payload=payload,
        )

    def generate_custom_ai_report(
        self,
        current_user: User,
        patient_id: int,
        *,
        payload: CustomAiReportCreateRequest,
        token_secret: str | None,
        api_key: str | None,
        model_name: str,
        max_input_tokens: int,
        max_output_tokens: int,
        max_cost_usd: float,
        input_cost_per_million_usd: float | None,
        output_cost_per_million_usd: float | None,
    ) -> CustomAiReportResponse:
        self._require_report_role(current_user)
        self._require_patient_access(current_user, patient_id)
        if (
            not token_secret
            or len(token_secret) < CustomReportPreviewService.MINIMUM_TOKEN_SECRET_LENGTH
            or not api_key
            or input_cost_per_million_usd is None
            or output_cost_per_million_usd is None
            or max_input_tokens <= 0
            or max_output_tokens <= 0
            or max_cost_usd <= 0
            or input_cost_per_million_usd < 0
            or output_cost_per_million_usd < 0
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Custom AI report generation is not configured",
            )
        policy = CustomReportCostPolicy(
            model_name=model_name,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            max_cost_usd=Decimal(str(max_cost_usd)),
            input_cost_per_million_usd=Decimal(str(input_cost_per_million_usd)),
            output_cost_per_million_usd=Decimal(str(output_cost_per_million_usd)),
        )
        return CustomReportGenerationService(
            self.db,
            token_secret=token_secret,
            api_key=api_key,
            cost_policy=policy,
        ).generate(
            patient_id=patient_id,
            requested_by_user_id=current_user.id,
            payload=payload,
        )

    def list_custom_ai_reports(
        self,
        current_user: User,
        patient_id: int,
        *,
        pagination: PaginationParams,
        report_status: str | None,
    ) -> CustomAiReportListResponse:
        self._require_report_role(current_user)
        self._require_patient_access(current_user, patient_id)
        return CustomReportHistoryService(self.db).list_reports(
            patient_id,
            pagination=pagination,
            report_status=report_status,
        )

    def get_custom_ai_report(
        self,
        current_user: User,
        patient_id: int,
        report_id: int,
    ) -> CustomAiReportResponse:
        self._require_report_role(current_user)
        self._require_patient_access(current_user, patient_id)
        return CustomReportHistoryService(self.db).get_report(patient_id, report_id)

    @staticmethod
    def _current_week_start(now: datetime | None = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _get_access_profile(self, current_user: User) -> ProfessionalProfile | None:
        return AccessPolicy(self.db, current_user).require_active_professional_profile()

    @staticmethod
    def _require_report_role(current_user: User) -> None:
        """Allow administrators to use report tools without a professional role."""
        if not is_admin(current_user):
            require_role(current_user, RoleNameEnum.PROFESSIONAL)

    def _require_patient_access(self, current_user: User, patient_id: int) -> User:
        return AccessPolicy(self.db, current_user).require_professional_patient_read(patient_id)

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
            anamnese_text = AnamneseClinicalService.hydrate(anamnese).info
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
