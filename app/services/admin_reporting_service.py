from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    AdminCostEntry,
    AiReportCache,
    AiReportStatusEnum,
    DailyReport,
    MonitoringPlan,
    ProfessionalProfile,
    RoleNameEnum,
    User,
)
from app.models.schemas import (
    AdminCostEntryCreate,
    AdminCostEntryRead,
    AdminCostSummary,
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
        manual_cost_total_cents = sum(entry.amount_cents for entry in manual_entries)

        return AdminCostSummary(
            start_date=resolved_start,
            end_date=resolved_end,
            ai_report_count=ai_report_count,
            ai_report_cost_usd=round(ai_report_cost_usd, 2),
            whatsapp_message_count=whatsapp_message_count,
            whatsapp_cost_per_message_cents=cost_per_message,
            whatsapp_cost_cents=whatsapp_cost_cents,
            manual_cost_entries=manual_entries,
            manual_cost_total_cents=manual_cost_total_cents,
        )

    def list_cost_entries(self, *, start_date: date | None = None, end_date: date | None = None) -> list[AdminCostEntryRead]:
        query = self.db.query(AdminCostEntry)
        if start_date:
            query = query.filter(AdminCostEntry.incurred_on >= start_date)
        if end_date:
            query = query.filter(AdminCostEntry.incurred_on <= end_date)
        entries = query.order_by(AdminCostEntry.incurred_on.desc(), AdminCostEntry.id.desc()).all()
        return [AdminCostEntryRead.model_validate(entry) for entry in entries]

    def create_cost_entry(self, current_user: User, payload: AdminCostEntryCreate) -> AdminCostEntryRead:
        entry = AdminCostEntry(
            description=payload.description,
            category=payload.category,
            amount_cents=payload.amount_cents,
            incurred_on=payload.incurred_on,
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
