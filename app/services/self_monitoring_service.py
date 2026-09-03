from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import json
import math

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.security_context import set_database_service_context
from app.models.models import Anamnese, MonitoringPlan, MonitoringPlanOriginEnum, SelfMonitoringInsight, User
from app.models.schemas import (
    CustomClinicalSummary,
    PatientDashboardPagination,
    SelfMonitoringInsightListItem,
    SelfMonitoringInsightListResponse,
    SelfMonitoringInsightRead,
)
from app.services.anamnese_clinical_service import AnamneseClinicalService
from app.services.custom_report_service import CustomReportService
from app.services.insight_service import InsightService
from app.services.payment_service import PaymentService
from app.services.self_monitoring_insight_clinical_service import SelfMonitoringInsightClinicalService

DEFAULT_EVOLUTION_PERIOD_DAYS = 30
INSIGHT_COOLDOWN_DAYS = 15
INSIGHT_PROMPT_OVERHEAD_TOKENS = 400


@dataclass(frozen=True)
class InsightCostPolicy:
    api_key: str
    model_name: str
    max_input_tokens: int
    max_output_tokens: int
    max_cost_usd: Decimal
    input_cost_per_million_usd: Decimal
    output_cost_per_million_usd: Decimal


class SelfMonitoringService:
    """Self-registered patient monitoring their own symptoms, with no professional involved.

    Every method here trusts only `current_user.id` as the patient scope — there is no
    AccessPolicy/professional link check, by design, since this flow exists specifically
    for patients who are not under a professional's care on the platform.
    """

    def __init__(self, db: Session):
        self.db = db

    def create_or_reactivate_plan(self, current_user: User) -> MonitoringPlan:
        existing = (
            self.db.query(MonitoringPlan)
            .filter(
                MonitoringPlan.patient_id == current_user.id,
                MonitoringPlan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value,
                MonitoringPlan.active.is_(True),
            )
            .first()
        )
        if existing:
            return existing

        # The monitoring_plans_insert RLS policy (alembic 0009) only allows
        # admins, professionals, or service context to INSERT — a plain patient
        # identity is rejected even for their own row, so this provisioning
        # step needs service context, same as ProfessionalService.create_patient.
        set_database_service_context(self.db, "self_monitoring_provisioning")
        plan = MonitoringPlan(
            patient_id=current_user.id,
            title="Automonitoramento",
            active=True,
            # Naive date.today() reads the server's OS clock (UTC on EC2), not
            # Brazil's calendar day — during ~21h-24h BRT that's already
            # "tomorrow" in UTC, which pushed start_date past today and made
            # _get_active_plan's `start_date <= today` filter (computed in
            # SCHEDULER_TIMEZONE) reject a plan created minutes earlier.
            start_date=datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date(),
            origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)

        return plan

    def evolution_report(
        self,
        current_user: User,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> CustomClinicalSummary:
        if not PaymentService(self.db).has_access(current_user):
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="SUBSCRIPTION_REQUIRED")
        resolved_end = end_date or datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()
        resolved_start = start_date or (resolved_end - timedelta(days=DEFAULT_EVOLUTION_PERIOD_DAYS - 1))
        return CustomReportService(self.db).build_summary(current_user.id, resolved_start, resolved_end)

    def insight_report(
        self,
        current_user: User,
        *,
        api_key: str | None,
        model_name: str,
        max_input_tokens: int,
        max_output_tokens: int,
        max_cost_usd: float,
        input_cost_per_million_usd: float | None,
        output_cost_per_million_usd: float | None,
        now: datetime | None = None,
    ) -> SelfMonitoringInsightRead:
        """A supportive, non-diagnostic AI summary of the patient's own evolution.

        Deliberately reuses the exact same `resumo_paciente` mode/prompt as
        the professional flow's cost-cap plumbing, but with no diagnostic
        hypothesis, urgency, or hospital-referral content — see
        `InsightService._prompt_resumo_paciente`. Trusts only
        `current_user.id`, same as `evolution_report` above.
        """
        if not PaymentService(self.db).has_access(current_user):
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="SUBSCRIPTION_REQUIRED")

        now = now or datetime.now(timezone.utc)
        end_date = datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()
        start_date = end_date - timedelta(days=DEFAULT_EVOLUTION_PERIOD_DAYS - 1)
        summary = CustomReportService(self.db).build_summary(current_user.id, start_date, end_date)

        if not summary.sufficient_data:
            return SelfMonitoringInsightRead(
                patient_id=current_user.id,
                start_date=start_date,
                end_date=end_date,
                sufficient_data=False,
            )

        latest = (
            self.db.query(SelfMonitoringInsight)
            .filter(SelfMonitoringInsight.patient_id == current_user.id)
            .order_by(SelfMonitoringInsight.generated_at.desc())
            .first()
        )
        if latest and latest.next_generation_at and self._as_utc(latest.next_generation_at) > now:
            SelfMonitoringInsightClinicalService.hydrate(latest)
            return self._response(latest, sufficient_data=True)

        if (
            not api_key
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
                detail="Self-monitoring insight generation is not configured",
            )
        cost_policy = InsightCostPolicy(
            api_key=api_key,
            model_name=model_name,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            max_cost_usd=Decimal(str(max_cost_usd)),
            input_cost_per_million_usd=Decimal(str(input_cost_per_million_usd)),
            output_cost_per_million_usd=Decimal(str(output_cost_per_million_usd)),
        )

        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == current_user.id).first()
        anamnese_text = AnamneseClinicalService.hydrate(anamnese).info if anamnese else "Anamnese não registrada."
        clinical_text = "\n\n".join([
            "ANAMNESE DO PACIENTE:",
            anamnese_text,
            "DADOS DE AUTOMONITORAMENTO:",
            json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")),
        ])
        estimated_input_tokens = math.ceil(len(clinical_text) / 4) + INSIGHT_PROMPT_OVERHEAD_TOKENS
        if estimated_input_tokens > cost_policy.max_input_tokens:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="REPORT_INPUT_TOO_LARGE")
        estimated_cost = self._calculate_cost(cost_policy, estimated_input_tokens, cost_policy.max_output_tokens)
        if estimated_cost > cost_policy.max_cost_usd:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="REPORT_COST_LIMIT_EXCEEDED")

        try:
            result = InsightService(
                api_key=cost_policy.api_key,
                modo="resumo_paciente",
                model=cost_policy.model_name,
                max_tokens=cost_policy.max_output_tokens,
            ).gerar_interpretacao_com_uso(clinical_text)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "AI_GENERATION_FAILED"},
            ) from exc

        generated_at = datetime.now(timezone.utc)
        # Always a new row now (self_monitoring_insights is a history table,
        # see alembic 0025) -- never reuse `latest`, or regenerating would
        # silently overwrite the previous entry in the patient's history.
        record = SelfMonitoringInsight(patient_id=current_user.id)
        record.start_date = start_date
        record.end_date = end_date
        record.input_tokens = result.input_tokens
        record.output_tokens = result.output_tokens
        record.actual_cost = self._calculate_cost(cost_policy, result.input_tokens, result.output_tokens)
        record.model_name = cost_policy.model_name
        record.generated_at = generated_at
        record.next_generation_at = generated_at + timedelta(days=INSIGHT_COOLDOWN_DAYS)
        set_database_service_context(self.db, "self_monitoring_insight_generation")
        self.db.add(record)
        self.db.flush()
        SelfMonitoringInsightClinicalService.write_response(record, result.data)
        self.db.commit()
        self.db.refresh(record)
        SelfMonitoringInsightClinicalService.hydrate(record)
        return self._response(record, sufficient_data=True)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _calculate_cost(cost_policy: InsightCostPolicy, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal("1000000")
        return (
            Decimal(input_tokens) * cost_policy.input_cost_per_million_usd / million
            + Decimal(output_tokens) * cost_policy.output_cost_per_million_usd / million
        ).quantize(Decimal("0.00000001"))

    @staticmethod
    def _response(record: SelfMonitoringInsight, *, sufficient_data: bool) -> SelfMonitoringInsightRead:
        return SelfMonitoringInsightRead(
            id=record.id,
            patient_id=record.patient_id,
            start_date=record.start_date,
            end_date=record.end_date,
            sufficient_data=sufficient_data,
            insight=record.insight_response,
            generated_at=record.generated_at,
            next_generation_at=record.next_generation_at,
        )

    def list_insights(self, current_user: User, *, page: int, per_page: int) -> SelfMonitoringInsightListResponse:
        query = self.db.query(SelfMonitoringInsight).filter(SelfMonitoringInsight.patient_id == current_user.id)
        total = query.count()
        records = (
            query.order_by(SelfMonitoringInsight.generated_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return SelfMonitoringInsightListResponse(
            items=[
                SelfMonitoringInsightListItem(
                    id=record.id,
                    start_date=record.start_date,
                    end_date=record.end_date,
                    generated_at=record.generated_at,
                    next_generation_at=record.next_generation_at,
                )
                for record in records
            ],
            pagination=PatientDashboardPagination(
                page=page,
                per_page=per_page,
                total=total,
                total_pages=math.ceil(total / per_page) if total else 0,
            ),
        )

    def get_insight(self, current_user: User, insight_id: int) -> SelfMonitoringInsightRead:
        record = (
            self.db.query(SelfMonitoringInsight)
            .filter(SelfMonitoringInsight.patient_id == current_user.id, SelfMonitoringInsight.id == insight_id)
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSIGHT_NOT_FOUND")
        SelfMonitoringInsightClinicalService.hydrate(record)
        return self._response(record, sufficient_data=True)
