from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.billing_plans import get_professional_plan, get_self_monitoring_plan
from app.core.config import settings
from app.core.permissions import has_role
from app.models.models import (
    AdminCostEntry,
    AiReportCache,
    AiReportStatusEnum,
    DailyReport,
    MonitoringPlan,
    ProfessionalProfile,
    RoleNameEnum,
    SelfMonitoringInsight,
    Subscription,
    SubscriptionStatusEnum,
    User,
    WhatsAppMessage,
)
from app.models.schemas import (
    AdminBillingSummary,
    AdminCostEntryCreate,
    AdminCostEntryRead,
    AdminCostSummary,
    AdminSystemHealth,
    AdminUserRead,
    AdminUserStatusEnum,
    AdminWhatsappDailyPoint,
    AdminWhatsappStats,
)


class AdminReportingService:
    """Read-only aggregates for the super-admin dashboard: who's on the
    platform, and what it's costing to run — built directly from data this
    app already has, never from invented/placeholder numbers.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_users(
        self,
        *,
        role: str | None = None,
        status: AdminUserStatusEnum | None = None,
        search: str | None = None,
    ) -> list[AdminUserRead]:
        active_patient_ids = {
            row[0]
            for row in self.db.query(MonitoringPlan.patient_id)
            .filter(MonitoringPlan.active.is_(True))
            .distinct()
            .all()
        }
        active_professional_user_ids = {
            row[0]
            for row in self.db.query(ProfessionalProfile.user_id)
            .filter(ProfessionalProfile.active.is_(True))
            .all()
        }

        def is_active(user: User) -> bool:
            roles = user.roles
            if RoleNameEnum.PATIENT.value in roles:
                return user.id in active_patient_ids
            if RoleNameEnum.PROFESSIONAL.value in roles:
                return user.id in active_professional_user_ids
            # Admins/super-admins have no plan/profile concept — always shown active.
            return True

        results: list[AdminUserRead] = []
        for user in self.db.query(User).order_by(User.created_at.desc()).all():
            roles = user.roles
            if role and role not in roles:
                continue
            user_status = AdminUserStatusEnum.ACTIVE if is_active(user) else AdminUserStatusEnum.INACTIVE
            if status and user_status != status:
                continue
            if search:
                needle = search.strip().lower()
                if needle not in (user.name or "").lower() and needle not in (user.email or "").lower():
                    continue
            results.append(
                AdminUserRead(
                    id=user.id,
                    name=user.name,
                    email=user.email,
                    phone=user.phone,
                    roles=roles,
                    status=user_status,
                    created_at=user.created_at,
                )
            )
        return results

    def cost_summary(self, *, start_date: date | None = None, end_date: date | None = None) -> AdminCostSummary:
        today = datetime.now(timezone.utc).date()
        resolved_end = end_date or today
        resolved_start = start_date or resolved_end.replace(day=1)

        ai_row = (
            self.db.query(func.count(AiReportCache.id), func.coalesce(func.sum(AiReportCache.actual_cost), 0))
            .filter(
                AiReportCache.status == AiReportStatusEnum.COMPLETED.value,
                func.date(AiReportCache.generated_at) >= resolved_start,
                func.date(AiReportCache.generated_at) <= resolved_end,
            )
            .one()
        )
        ai_report_count = int(ai_row[0] or 0)
        ai_report_cost_usd = float(ai_row[1] or 0)

        self_monitoring_row = (
            self.db.query(
                func.count(SelfMonitoringInsight.id),
                func.coalesce(func.sum(SelfMonitoringInsight.actual_cost), 0),
            )
            .filter(
                func.date(SelfMonitoringInsight.generated_at) >= resolved_start,
                func.date(SelfMonitoringInsight.generated_at) <= resolved_end,
            )
            .one()
        )
        self_monitoring_report_count = int(self_monitoring_row[0] or 0)
        self_monitoring_cost_usd = float(self_monitoring_row[1] or 0)

        whatsapp_message_count = (
            self.db.query(func.count(DailyReport.id))
            .filter(
                DailyReport.prompt_sent_at.is_not(None),
                func.date(DailyReport.prompt_sent_at) >= resolved_start,
                func.date(DailyReport.prompt_sent_at) <= resolved_end,
            )
            .scalar()
            or 0
        )

        cost_per_message = settings.WHATSAPP_COST_PER_MESSAGE_CENTS
        whatsapp_cost_cents = whatsapp_message_count * cost_per_message if cost_per_message else None

        manual_entries = self.list_cost_entries(start_date=resolved_start, end_date=resolved_end)
        manual_cost_total_cents = sum(
            entry.amount_cents * self._recurring_occurrences(entry.incurred_on, resolved_start, resolved_end)
            if entry.is_recurring
            else entry.amount_cents
            for entry in manual_entries
        )

        return AdminCostSummary(
            start_date=resolved_start,
            end_date=resolved_end,
            ai_report_count=ai_report_count,
            ai_report_cost_usd=round(ai_report_cost_usd, 2),
            self_monitoring_report_count=self_monitoring_report_count,
            self_monitoring_cost_usd=round(self_monitoring_cost_usd, 2),
            whatsapp_message_count=whatsapp_message_count,
            whatsapp_cost_per_message_cents=cost_per_message,
            whatsapp_cost_cents=whatsapp_cost_cents,
            manual_cost_entries=manual_entries,
            manual_cost_total_cents=manual_cost_total_cents,
        )

    def list_cost_entries(self, *, start_date: date | None = None, end_date: date | None = None) -> list[AdminCostEntryRead]:
        query = self.db.query(AdminCostEntry)
        if end_date:
            query = query.filter(AdminCostEntry.incurred_on <= end_date)
        if start_date:
            # A recurring entry started before this period still applies to
            # it every month, so it stays listed even though its own
            # incurred_on falls before start_date -- a one-off entry doesn't.
            query = query.filter(
                or_(AdminCostEntry.incurred_on >= start_date, AdminCostEntry.is_recurring.is_(True))
            )
        entries = query.order_by(AdminCostEntry.incurred_on.desc(), AdminCostEntry.id.desc()).all()
        return [AdminCostEntryRead.model_validate(entry) for entry in entries]

    @staticmethod
    def _recurring_occurrences(incurred_on: date, start_date: date, end_date: date) -> int:
        """How many calendar months a recurring cost that started on
        incurred_on falls due within [start_date, end_date] -- one per month
        from whichever is later, incurred_on or start_date, through end_date.
        """
        range_start = max(start_date, incurred_on)
        if range_start > end_date:
            return 0
        return (end_date.year - range_start.year) * 12 + (end_date.month - range_start.month) + 1

    def create_cost_entry(self, current_user: User, payload: AdminCostEntryCreate) -> AdminCostEntryRead:
        entry = AdminCostEntry(
            description=payload.description,
            category=payload.category,
            amount_cents=payload.amount_cents,
            incurred_on=payload.incurred_on,
            is_recurring=payload.is_recurring,
            created_by_user_id=current_user.id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return AdminCostEntryRead.model_validate(entry)

    def delete_cost_entry(self, entry_id: int) -> None:
        entry = self.db.query(AdminCostEntry).filter(AdminCostEntry.id == entry_id).first()
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost entry not found")
        self.db.delete(entry)
        self.db.commit()

    def whatsapp_stats(self, *, days: int = 30) -> AdminWhatsappStats:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days - 1)

        rows = (
            self.db.query(func.date(DailyReport.prompt_sent_at).label("sent_date"), func.count(DailyReport.id))
            .filter(
                DailyReport.prompt_sent_at.is_not(None),
                func.date(DailyReport.prompt_sent_at) >= start,
                func.date(DailyReport.prompt_sent_at) <= today,
            )
            .group_by("sent_date")
            .order_by("sent_date")
            .all()
        )
        counts_by_date = {}
        for sent_date, count in rows:
            resolved_date = sent_date if isinstance(sent_date, date) else datetime.fromisoformat(str(sent_date)).date()
            counts_by_date[resolved_date] = int(count)

        daily = [
            AdminWhatsappDailyPoint(date=start + timedelta(days=offset), sent_count=counts_by_date.get(start + timedelta(days=offset), 0))
            for offset in range(days)
        ]
        total_sent = sum(point.sent_count for point in daily)

        cost_per_message = settings.WHATSAPP_COST_PER_MESSAGE_CENTS
        estimated_cost_cents = total_sent * cost_per_message if cost_per_message else None

        return AdminWhatsappStats(
            period_days=days,
            start_date=start,
            end_date=today,
            total_sent=total_sent,
            daily=daily,
            cost_per_message_cents=cost_per_message,
            estimated_cost_cents=estimated_cost_cents,
        )

    def system_health(self) -> AdminSystemHealth:
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)

        last_inbound = self.db.query(func.max(WhatsAppMessage.created_at)).scalar()
        last_outbound = self.db.query(func.max(DailyReport.prompt_sent_at)).scalar()

        processed_24h = (
            self.db.query(func.count(WhatsAppMessage.id))
            .filter(WhatsAppMessage.status == "PROCESSED", WhatsAppMessage.created_at >= since_24h)
            .scalar()
            or 0
        )
        failed_24h = (
            self.db.query(func.count(WhatsAppMessage.id))
            .filter(WhatsAppMessage.status == "FAILED", WhatsAppMessage.created_at >= since_24h)
            .scalar()
            or 0
        )
        active_plans = self.db.query(func.count(MonitoringPlan.id)).filter(MonitoringPlan.active.is_(True)).scalar() or 0

        return AdminSystemHealth(
            checked_at=now,
            last_inbound_message_at=last_inbound,
            last_outbound_message_at=last_outbound,
            processed_messages_last_24h=int(processed_24h),
            failed_messages_last_24h=int(failed_24h),
            active_monitoring_plans=int(active_plans),
        )

    def billing_summary(self) -> AdminBillingSummary:
        active_rows = (
            self.db.query(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .filter(Subscription.status == SubscriptionStatusEnum.ACTIVE.value)
            .all()
        )

        mrr_cents = 0
        for subscription, user in active_rows:
            if not subscription.plan_id:
                continue
            resolve_plan = get_professional_plan if has_role(user, RoleNameEnum.PROFESSIONAL) else get_self_monitoring_plan
            plan = resolve_plan(subscription.plan_id)
            if plan and plan.months:
                mrr_cents += round(plan.price_cents / plan.months)

        trialing_count = (
            self.db.query(Subscription).filter(Subscription.status == SubscriptionStatusEnum.TRIALING.value).count()
        )
        past_due_count = (
            self.db.query(Subscription).filter(Subscription.status == SubscriptionStatusEnum.PAST_DUE.value).count()
        )
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        canceled_last_30d = (
            self.db.query(Subscription)
            .filter(Subscription.status == SubscriptionStatusEnum.CANCELED.value, Subscription.updated_at >= thirty_days_ago)
            .count()
        )

        active_count = len(active_rows)
        churn_denominator = active_count + canceled_last_30d
        churn_rate = (canceled_last_30d / churn_denominator) if churn_denominator else 0.0

        return AdminBillingSummary(
            mrr_cents=mrr_cents,
            active_subscriptions=active_count,
            trialing_subscriptions=trialing_count,
            past_due_subscriptions=past_due_count,
            canceled_last_30d=canceled_last_30d,
            churn_rate=round(churn_rate, 4),
        )
