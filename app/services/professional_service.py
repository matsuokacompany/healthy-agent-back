import hashlib
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.models import (
    AiReportCache,
    AiReportStatusEnum,
    Allergy,
    Anamnese,
    DailyReport,
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    RoleNameEnum,
    Supplement,
    User,
)
from app.models.schemas import (
    AiReportFeedbackResponse,
    AllergyCreate,
    AllergyUpdate,
    AnamneseRead,
    PatientDashboardCalendarResponse,
    PatientDashboardCheckinsResponse,
    PatientDashboardResponseV2,
    PatientTopSymptomTermsResponse,
    ProfessionalAiReportResponse,
    ProfessionalDashboardAdherenceEntry,
    ProfessionalDashboardMonthlySymptomCount,
    ProfessionalDashboardOverview,
    ProfessionalDashboardRedFlag,
    ProfessionalPatientRead,
    ProfessionalPatientCreate,
    ProfessionalPatientCreateResponse,
    CustomAiReportPreviewRequest,
    CustomAiReportPreviewResponse,
    CustomAiReportCreateRequest,
    CustomAiReportResponse,
    CustomAiReportListResponse,
    SupplementCreate,
    SupplementUpdate,
)
from app.core.auth import assign_role, invite_supabase_user
from app.core.access_policy import AccessPolicy
from app.core.permissions import is_admin, require_role
from app.services.ai_report_clinical_service import AiReportClinicalService
from app.services.insight_service import InsightService
from app.services.custom_report_preview_service import CustomReportPreviewService
from app.services.custom_report_generation_service import CustomReportCostPolicy, CustomReportGenerationService
from app.services.custom_report_history_service import CustomReportHistoryService
from app.services.notification_service import notify_ai_report_ready
from app.services.patient_dashboard_service import PaginationParams, PatientDashboardService, ReportFilters
from app.db.security_context import set_database_service_context
from app.services.payment_service import PaymentService
from app.services.professional_capacity_service import patient_has_own_subscription, require_patient_cap
from app.services.report_service import ReportService
from app.services.anamnese_clinical_service import AnamneseClinicalService
from app.services.allergy_service import AllergyService
from app.services.red_flag_symptoms import RED_FLAG_CATEGORY_BY_KEY
from app.services.supplement_service import SupplementService


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
        self._require_billing_access(profile)
        require_patient_cap(self.db, profile)
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
        for supplement in payload.supplements:
            self.db.add(
                Supplement(
                    patient_id=patient.id,
                    name=supplement.name,
                    dosage_times=supplement.dosage_times,
                    dosage_period=supplement.dosage_period.value,
                    duration_days=supplement.duration_days,
                )
            )
        for allergy in payload.allergies:
            self.db.add(
                Allergy(
                    patient_id=patient.id,
                    allergen=allergy.allergen,
                    severity=allergy.severity.value,
                )
            )
        self.db.commit()
        self.db.refresh(patient)
        self.db.refresh(plan)

        invited_supabase_user_id = invite_supabase_user(patient.email, name=patient.name)
        if invited_supabase_user_id:
            patient.supabase_user_id = invited_supabase_user_id
            self.db.commit()
            self.db.refresh(patient)

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
        symptom_counts_by_patient: dict[int, int] = {}
        for plan in plans:
            if not plan.patient:
                continue
            last_report = self._get_last_report(plan.patient_id, plan.id)
            existing = patient_items.get(plan.patient_id)
            if plan.patient_id not in symptom_counts_by_patient:
                # Scoped to the patient, not this one plan -- a patient can
                # end up with more than one MonitoringPlan row (self-service
                # -> professional conversion, a relink creating a new plan)
                # and symptomatic check-ins from an older plan are just as
                # real as ones from the plan that happens to have the most
                # recent check-in. Matches the unbounded, patient-scoped
                # queries the patient detail page's Check-ins/calendar/
                # symptom-ranking views already use (PatientDashboardService
                # ._reports_query / ._get_top_symptom_terms) -- this count
                # used to be plan- and 30-day-scoped and would silently
                # under-count relative to what the professional sees there.
                symptom_counts_by_patient[plan.patient_id] = self._count_symptom_reports(plan.patient_id)
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
                symptom_reports_count=symptom_counts_by_patient[plan.patient_id],
                has_own_subscription=patient_has_own_subscription(self.db, plan.patient_id),
            )
            if existing is None or (item.last_checkin_at or datetime.min.replace(tzinfo=timezone.utc)) > (
                existing.last_checkin_at or datetime.min.replace(tzinfo=timezone.utc)
            ):
                patient_items[plan.patient_id] = item
        return list(patient_items.values())

    # How far back to look for red-flag events on the overview dashboard --
    # a rolling window, not "since the plan started", so the list stays
    # short and recent rather than accumulating forever.
    DASHBOARD_RED_FLAG_LOOKBACK_DAYS = 14
    DASHBOARD_RED_FLAG_LIMIT = 15
    DASHBOARD_TOP_SYMPTOMS_LIMIT = 8
    DASHBOARD_ADHERENCE_WINDOW_DAYS = 30
    DASHBOARD_SYMPTOMS_BY_MONTH_MONTHS = 6

    def get_dashboard_overview(self, current_user: User) -> ProfessionalDashboardOverview:
        profile = self._get_access_profile(current_user)
        patient_ids = self._active_patient_ids(profile)
        if not patient_ids:
            return ProfessionalDashboardOverview(active_patients=0)

        since = datetime.now(timezone.utc).date() - timedelta(days=self.DASHBOARD_RED_FLAG_LOOKBACK_DAYS)
        rows = (
            self.db.query(DailyReport, User.name)
            .join(User, User.id == DailyReport.user_id)
            .filter(
                DailyReport.user_id.in_(patient_ids),
                DailyReport.red_flag_category.isnot(None),
                DailyReport.report_date >= since,
            )
            .order_by(DailyReport.report_date.desc())
            .limit(self.DASHBOARD_RED_FLAG_LIMIT)
            .all()
        )
        red_flags: list[ProfessionalDashboardRedFlag] = []
        for report, patient_name in rows:
            category = RED_FLAG_CATEGORY_BY_KEY.get(report.red_flag_category)
            if not category:
                continue
            red_flags.append(
                ProfessionalDashboardRedFlag(
                    patient_id=report.user_id,
                    patient_name=patient_name,
                    report_date=report.report_date,
                    category_key=category.key,
                    category_label=category.label,
                    tier=category.tier,
                )
            )

        top_symptoms = self.dashboard_service.get_top_symptom_terms_for_patients(
            patient_ids, limit=self.DASHBOARD_TOP_SYMPTOMS_LIMIT
        ).items

        adherence_since = datetime.now(timezone.utc).date() - timedelta(days=self.DASHBOARD_ADHERENCE_WINDOW_DAYS)
        adherence_rows = (
            self.db.query(DailyReport.user_id, DailyReport.completed)
            .filter(DailyReport.user_id.in_(patient_ids), DailyReport.report_date >= adherence_since)
            .all()
        )
        total_by_patient: dict[int, int] = {}
        completed_by_patient: dict[int, int] = {}
        for patient_id, completed in adherence_rows:
            total_by_patient[patient_id] = total_by_patient.get(patient_id, 0) + 1
            if completed:
                completed_by_patient[patient_id] = completed_by_patient.get(patient_id, 0) + 1
        patient_names = dict(self.db.query(User.id, User.name).filter(User.id.in_(patient_ids)).all())
        adherence = [
            ProfessionalDashboardAdherenceEntry(
                patient_id=patient_id,
                patient_name=patient_names.get(patient_id, ""),
                adherence_percentage=self._percentage(completed_by_patient.get(patient_id, 0), total),
            )
            for patient_id, total in total_by_patient.items()
        ]
        adherence.sort(key=lambda entry: entry.adherence_percentage)

        months_since = datetime.now(timezone.utc).date() - timedelta(
            days=30 * self.DASHBOARD_SYMPTOMS_BY_MONTH_MONTHS
        )
        symptom_dates = (
            self.db.query(DailyReport.report_date)
            .filter(
                DailyReport.user_id.in_(patient_ids),
                DailyReport.had_symptoms.is_(True),
                DailyReport.report_date >= months_since,
            )
            .all()
        )
        counts_by_month: dict[str, int] = {}
        for (report_date,) in symptom_dates:
            month_key = report_date.strftime("%Y-%m")
            counts_by_month[month_key] = counts_by_month.get(month_key, 0) + 1
        symptoms_by_month = [
            ProfessionalDashboardMonthlySymptomCount(month=month, count=count)
            for month, count in sorted(counts_by_month.items())
        ]

        return ProfessionalDashboardOverview(
            active_patients=len(patient_ids),
            red_flags=red_flags,
            top_symptoms=top_symptoms,
            adherence=adherence,
            symptoms_by_month=symptoms_by_month,
        )

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        return round((numerator / denominator * 100), 1) if denominator else 0.0

    def _active_patient_ids(self, profile: ProfessionalProfile | None) -> list[int]:
        query = self.db.query(MonitoringPlan.patient_id).filter(MonitoringPlan.active.is_(True))
        if profile:
            query = query.join(MonitoringProfessional).filter(
                MonitoringProfessional.professional_profile_id == profile.id,
                MonitoringProfessional.active.is_(True),
            )
        return [row[0] for row in query.distinct().all()]

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

    def get_top_symptom_terms(self, current_user: User, patient_id: int, *, limit: int = 6) -> PatientTopSymptomTermsResponse:
        self._require_patient_access(current_user, patient_id)
        return self.dashboard_service.get_top_symptom_terms_for_patients([patient_id], limit=limit)

    def get_calendar(
        self,
        current_user: User,
        patient_id: int,
        *,
        year: int,
        month: int,
    ) -> PatientDashboardCalendarResponse:
        self._require_patient_access(current_user, patient_id)
        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        reports = (
            self.dashboard_service._reports_query(patient_id, ReportFilters(start_date=start_date, end_date=end_date))
            .order_by(DailyReport.report_date.asc(), DailyReport.prompt_sent_at.asc(), DailyReport.id.asc())
            .all()
        )

        reports_by_day: dict[date, list[DailyReport]] = {}
        for report in reports:
            reports_by_day.setdefault(report.report_date, []).append(report)

        days = [
            self.dashboard_service._build_calendar_day(date(year, month, day), reports_by_day.get(date(year, month, day), []))
            for day in range(1, last_day + 1)
        ]
        return PatientDashboardCalendarResponse(year=year, month=month, days=days)

    def get_anamnese(self, current_user: User, patient_id: int) -> AnamneseRead:
        self._require_patient_access(current_user, patient_id)
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if not anamnese:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anamnese not found")
        return AnamneseClinicalService.hydrate(anamnese)

    def create_anamnese(
        self,
        current_user: User,
        patient_id: int,
        info: str,
        risk_factors: dict | None = None,
        allergies: dict | None = None,
    ) -> Anamnese:
        self._require_patient_access(current_user, patient_id)
        if self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient already has an anamnese",
            )
        anamnese = Anamnese(
            user_id=patient_id,
            info=AnamneseClinicalService.initial_plaintext(info),
        )
        self.db.add(anamnese)
        try:
            self.db.flush()
            AnamneseClinicalService.write(anamnese, info)
            if risk_factors:
                AnamneseClinicalService.write_risk_factors(anamnese, risk_factors)
            if allergies:
                AnamneseClinicalService.write_allergies(anamnese, allergies)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient already has an anamnese",
            )
        self.db.refresh(anamnese)
        return AnamneseClinicalService.hydrate(anamnese)

    def update_anamnese(
        self,
        current_user: User,
        patient_id: int,
        info: str,
        risk_factors: dict | None = None,
        allergies: dict | None = None,
    ) -> Anamnese:
        self._require_patient_access(current_user, patient_id)
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if not anamnese:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anamnese not found")
        AnamneseClinicalService.write(anamnese, info)
        if risk_factors:
            AnamneseClinicalService.write_risk_factors(anamnese, risk_factors)
        if allergies:
            AnamneseClinicalService.write_allergies(anamnese, allergies)
        self.db.commit()
        self.db.refresh(anamnese)
        return AnamneseClinicalService.hydrate(anamnese)

    def list_supplements(self, current_user: User, patient_id: int) -> list[Supplement]:
        self._require_patient_access(current_user, patient_id)
        return SupplementService(self.db).list_for_patient(patient_id)

    def create_supplement(
        self,
        current_user: User,
        patient_id: int,
        payload: SupplementCreate,
    ) -> Supplement:
        self._require_patient_access(current_user, patient_id)
        return SupplementService(self.db).create_for_patient(
            patient_id,
            payload.name,
            dosage_times=payload.dosage_times,
            dosage_period=payload.dosage_period,
            duration_days=payload.duration_days,
        )

    def update_supplement(
        self,
        current_user: User,
        patient_id: int,
        supplement_id: int,
        payload: SupplementUpdate,
    ) -> Supplement | None:
        self._require_patient_access(current_user, patient_id)
        return SupplementService(self.db).update_for_patient(
            patient_id, supplement_id, **payload.model_dump(exclude_unset=True)
        )

    def delete_supplement(self, current_user: User, patient_id: int, supplement_id: int) -> bool:
        self._require_patient_access(current_user, patient_id)
        return SupplementService(self.db).delete_for_patient(patient_id, supplement_id)

    def list_allergies(self, current_user: User, patient_id: int) -> list[Allergy]:
        self._require_patient_access(current_user, patient_id)
        return AllergyService(self.db).list_for_patient(patient_id)

    def create_allergy(
        self,
        current_user: User,
        patient_id: int,
        payload: AllergyCreate,
    ) -> Allergy:
        self._require_patient_access(current_user, patient_id)
        return AllergyService(self.db).create_for_patient(patient_id, payload.allergen, severity=payload.severity)

    def update_allergy(
        self,
        current_user: User,
        patient_id: int,
        allergy_id: int,
        payload: AllergyUpdate,
    ) -> Allergy | None:
        self._require_patient_access(current_user, patient_id)
        return AllergyService(self.db).update_for_patient(
            patient_id, allergy_id, **payload.model_dump(exclude_unset=True)
        )

    def delete_allergy(self, current_user: User, patient_id: int, allergy_id: int) -> bool:
        self._require_patient_access(current_user, patient_id)
        return AllergyService(self.db).delete_for_patient(patient_id, allergy_id)

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
        patient = self._require_patient_access(current_user, patient_id)
        self._require_billing_access(self._get_access_profile(current_user))
        clinical_summary = self._build_clinical_summary(patient_id, periodo)
        if modo == "preventivo":
            cooldown_days = InsightService.PREVENTIVE_REPORT_COOLDOWN_DAYS
            window_start = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
        else:
            cooldown_days = 30
            window_start = self._current_week_start()
        cached_report = (
            self.db.query(AiReportCache)
            .filter(AiReportCache.patient_id == patient_id)
            .filter(AiReportCache.modo == modo)
            .filter(AiReportCache.created_at >= window_start)
            .order_by(AiReportCache.created_at.desc(), AiReportCache.id.desc())
            .first()
        )
        if cached_report:
            AiReportClinicalService.hydrate(cached_report)
            return ProfessionalAiReportResponse(
                report_id=cached_report.id,
                patient_id=patient_id,
                periodo=cached_report.periodo,
                modo=cached_report.modo,
                clinical_summary=cached_report.clinical_summary,
                ai=cached_report.ai_response,
                professional_feedback=cached_report.professional_feedback,
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
                next_generation_at=generated_at + timedelta(days=cooldown_days),
            )
        self.db.add(report)
        self.db.flush()
        AiReportClinicalService.write_summary(report, clinical_summary)
        AiReportClinicalService.write_response(report, ai)
        notify_ai_report_ready(self.db, patient=patient, generated_by_user_id=current_user.id)
        self.db.commit()
        return ProfessionalAiReportResponse(
            report_id=report.id,
            patient_id=patient_id,
            periodo=periodo,
            modo=modo,
            clinical_summary=clinical_summary,
            ai=ai,
            professional_feedback=None,
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
        self._require_billing_access(self._get_access_profile(current_user))
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
        self._require_billing_access(self._get_access_profile(current_user))
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

    def set_ai_report_feedback(
        self,
        current_user: User,
        patient_id: int,
        report_id: int,
        *,
        feedback: str | None,
    ) -> AiReportFeedbackResponse:
        """Lets the requesting professional mark whether an AI report's
        hypothesis was useful, directly from the report view -- read access
        to the patient is enough (same level list/get_custom_ai_report use):
        this is an annotation on something already visible, not a new
        clinical write. Works for both the weekly quick view and a
        "personalizado" custom report, since both are AiReportCache rows."""
        self._require_report_role(current_user)
        self._require_patient_access(current_user, patient_id)
        report = (
            self.db.query(AiReportCache)
            .filter(AiReportCache.id == report_id, AiReportCache.patient_id == patient_id)
            .first()
        )
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI report not found")
        report.professional_feedback = feedback
        self.db.commit()
        return AiReportFeedbackResponse(report_id=report.id, professional_feedback=report.professional_feedback)

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

    def _require_billing_access(self, profile: ProfessionalProfile | None) -> None:
        """Soft-lock non-paying professionals out of new-patient/report actions.

        None means the caller is an admin acting without a professional
        profile (see require_active_professional_profile) — admins always
        pass. Read-only professional actions (list_patients, get_dashboard,
        get_checkins, get_anamnese, list/get custom reports) intentionally
        never call this: a professional past their grace period keeps full
        visibility into patients they already have, and the WhatsApp
        scheduler is untouched — only new-patient creation and new AI report
        generation are gated.
        """
        if profile is None:
            return
        if not PaymentService(self.db).has_professional_access(profile):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="PROFESSIONAL_SUBSCRIPTION_REQUIRED",
            )

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
        )

    # Capped (well under InsightService.MAX_REPORT_CHARS) so the check-in
    # report that follows always survives gerar_interpretacao_com_uso's
    # silent truncation, no matter how long the anamnese is. Order is kept
    # anamnese-first — health-agent-front's AiReportsJourney.tsx strips a
    # leading "ANAMNESE DO PACIENTE:" label off clinical_summary to render
    # the patient narrative, so this string must keep starting with it.
    MAX_ANAMNESE_CHARS_IN_SUMMARY = 2000

    def _build_clinical_summary(self, patient_id: int, periodo: str) -> str:
        report_text = ReportService(self.db).gerar_relatorio(patient_id, periodo)
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        if not anamnese:
            anamnese_text = "Anamnese não registrada."
        else:
            anamnese_text = AnamneseClinicalService.hydrate(anamnese).info
        return "\n\n".join([
            "ANAMNESE DO PACIENTE:",
            anamnese_text[: self.MAX_ANAMNESE_CHARS_IN_SUMMARY],
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

    def _count_symptom_reports(self, patient_id: int) -> int:
        # All-time, across every one of the patient's monitoring plans --
        # matches what the patient detail page's Check-ins tab, calendar,
        # and symptom-ranking card show by default (PatientDashboardService
        # ._reports_query / ._get_top_symptom_terms have no plan or date
        # restriction of their own), so this list's "Sintomas" column
        # doesn't silently disagree with what the professional counts by
        # hand once they open the patient.
        return int(
            self.db.query(func.count(DailyReport.id))
            .filter(
                DailyReport.user_id == patient_id,
                DailyReport.completed.is_(True),
                DailyReport.had_symptoms.is_(True),
            )
            .scalar()
            or 0
        )
