from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.security_context import set_database_service_context
from app.models.models import MonitoringPlan, MonitoringPlanOriginEnum, User
from app.models.schemas import CustomClinicalSummary
from app.services.custom_report_service import CustomReportService
from app.services.payment_service import PaymentService

DEFAULT_EVOLUTION_PERIOD_DAYS = 30


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
            # Self-healing for plans that predate this feature: guarantees
            # every self-service patient with an active plan has at least a
            # started trial, instead of silently having zero Subscription
            # row and getting blocked once access is enforced. No-op for
            # anyone who already has a trial/subscription going.
            PaymentService(self.db).start_trial_if_needed(current_user)
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
            start_date=date.today(),
            origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)

        # Starts the free trial the moment monitoring actually begins, not
        # whenever the billing page happens to be loaded first.
        PaymentService(self.db).start_trial_if_needed(current_user)

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
        resolved_end = end_date or date.today()
        resolved_start = start_date or (resolved_end - timedelta(days=DEFAULT_EVOLUTION_PERIOD_DAYS - 1))
        return CustomReportService(self.db).build_summary(current_user.id, resolved_start, resolved_end)
