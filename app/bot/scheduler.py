import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import or_, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.security_context import set_database_service_context
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    Notification,
    NotificationKindEnum,
    Subscription,
    User,
)
from app.services.daily_report_service import DailyReportService
from app.services.dunning_service import DunningService
from app.services.notification_service import notify_checkin_pending
from app.services.payment_service import subscription_grants_access

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
SCHEDULER_ADVISORY_LOCK_ID = 2026063001
DUNNING_ADVISORY_LOCK_ID = 2026063002
CHECKIN_REMINDER_ADVISORY_LOCK_ID = 2026063003


def _mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"***{digits[-4:]}"


def _is_postgresql_session(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _try_acquire_scheduler_lock(db, lock_id: int = SCHEDULER_ADVISORY_LOCK_ID) -> bool:
    if not _is_postgresql_session(db):
        logger.warning(
            "Scheduler advisory lock skipped because database dialect is not PostgreSQL | dialect=%s",
            db.get_bind().dialect.name,
        )
        return True

    return bool(
        db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        ).scalar()
    )


def _release_scheduler_lock(db, lock_id: int = SCHEDULER_ADVISORY_LOCK_ID) -> None:
    if not _is_postgresql_session(db):
        return

    db.execute(
        text("SELECT pg_advisory_unlock(:lock_id)"),
        {"lock_id": lock_id},
    )


async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:
    logger.info("SEND_PROMPT START | type=%s", check_type.value)

    db = SessionLocal()
    set_database_service_context(db, "scheduler")
    plans_processed = 0
    plans_skipped = 0
    plans_failed = 0
    lock_acquired = False

    try:
        lock_acquired = _try_acquire_scheduler_lock(db)
        if not lock_acquired:
            logger.info("SEND_PROMPT SKIPPED | type=%s reason=advisory_lock_busy", check_type.value)
            return

        tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        now = datetime.now(tz)
        today = now.date()
        report_date = today - timedelta(days=1)
        now_utc = now.astimezone(timezone.utc)

        plans = (
            db.query(MonitoringPlan)
            .join(User, MonitoringPlan.patient_id == User.id)
            .filter(MonitoringPlan.active.is_(True))
            .filter(or_(MonitoringPlan.start_date.is_(None), MonitoringPlan.start_date <= report_date))
            .filter(or_(MonitoringPlan.end_date.is_(None), MonitoringPlan.end_date >= report_date))
            .filter(User.phone.isnot(None))
            .all()
        )

        for plan in plans:
            user = plan.patient
            try:
                if plan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value:
                    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
                    if not subscription_grants_access(subscription):
                        plans_skipped += 1
                        continue

                channel = bot_manager.get_channel_for_user(user)
                if not channel or not user.phone:
                    plans_skipped += 1
                    continue

                report = DailyReportService.create_pending_report(
                    db=db,
                    user=user,
                    monitoring_plan=plan,
                    check_type=check_type,
                    now=now_utc,
                    report_date=report_date,
                )
                if report.completed:
                    db.rollback()
                    plans_skipped += 1
                    continue

                db.commit()
                db.refresh(report)

                wa_id = await channel.send_template(
                    user=user,
                    check_type=check_type,
                    report_date=report.report_date,
                )

                if wa_id and user.whatsapp_wa_id != wa_id:
                    user.whatsapp_wa_id = wa_id
                    db.commit()
                    logger.info(
                        "WhatsApp wa_id stored from send_template response | user_id=%s wa_id=%s",
                        user.id,
                        _mask_identifier(wa_id),
                    )

                plans_processed += 1

            except Exception:
                db.rollback()
                plans_failed += 1
                logger.exception("ERROR monitoring_plan_id=%s user_id=%s", plan.id, user.id if user else None)

    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_prompt")

    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db)
            except Exception:
                logger.exception("Failed to release scheduler advisory lock")
        db.close()

    logger.info(
        "SEND_PROMPT DONE | sent=%s skipped=%s failed=%s",
        plans_processed,
        plans_skipped,
        plans_failed,
    )


async def run_dunning_reminders() -> None:
    logger.info("DUNNING_REMINDERS START")

    db = SessionLocal()
    lock_acquired = False
    try:
        lock_acquired = _try_acquire_scheduler_lock(db, DUNNING_ADVISORY_LOCK_ID)
        if not lock_acquired:
            logger.info("DUNNING_REMINDERS SKIPPED | reason=advisory_lock_busy")
            return

        result = DunningService(db).run_daily_reminders()
        logger.info("DUNNING_REMINDERS DONE | %s", result)
    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR run_dunning_reminders")
    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db, DUNNING_ADVISORY_LOCK_ID)
            except Exception:
                logger.exception("Failed to release dunning advisory lock")
        db.close()


async def send_checkin_reminders() -> None:
    """In-app (not WhatsApp) nudge for a check-in still open late in the
    day. Runs once daily, so a report only ever gets one reminder even
    though this iterates every still-open report for today."""
    logger.info("CHECKIN_REMINDERS START")

    db = SessionLocal()
    set_database_service_context(db, "scheduler")
    lock_acquired = False
    reminders_sent = 0

    try:
        lock_acquired = _try_acquire_scheduler_lock(db, CHECKIN_REMINDER_ADVISORY_LOCK_ID)
        if not lock_acquired:
            logger.info("CHECKIN_REMINDERS SKIPPED | reason=advisory_lock_busy")
            return

        tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        today = datetime.now(tz).date()

        pending_reports = (
            db.query(DailyReport)
            .filter(DailyReport.report_date == today)
            .filter(DailyReport.completed.is_(False))
            .filter(
                DailyReport.status.in_(
                    [
                        DailyReportStatusEnum.PENDING,
                        DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION,
                        DailyReportStatusEnum.AWAITING_CAUSE,
                        DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE,
                    ]
                )
            )
            .all()
        )

        for report in pending_reports:
            already_reminded_today = (
                db.query(Notification)
                .filter(
                    Notification.user_id == report.user_id,
                    Notification.kind == NotificationKindEnum.CHECKIN_PENDING.value,
                    Notification.created_at >= datetime.now(timezone.utc) - timedelta(hours=12),
                )
                .first()
            )
            if already_reminded_today:
                continue
            notify_checkin_pending(db, patient_user_id=report.user_id)
            reminders_sent += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_checkin_reminders")
    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db, CHECKIN_REMINDER_ADVISORY_LOCK_ID)
            except Exception:
                logger.exception("Failed to release checkin reminder advisory lock")
        db.close()

    logger.info("CHECKIN_REMINDERS DONE | sent=%s", reminders_sent)


def start_scheduler(bot_manager):
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)

    _scheduler = AsyncIOScheduler(
        timezone=tz,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 1800,
        },
    )

    _scheduler.add_job(
        send_prompt,
        CronTrigger(
            hour=settings.SCHEDULER_MORNING_HOUR,
            minute=settings.SCHEDULER_MORNING_MINUTE,
            timezone=tz,
        ),
        args=[bot_manager, CheckTypeEnum.MORNING],
        id="morning",
        replace_existing=True,
    )

    _scheduler.add_job(
        run_dunning_reminders,
        CronTrigger(hour=9, minute=0, timezone=tz),
        id="dunning_reminders",
        replace_existing=True,
    )

    _scheduler.add_job(
        send_checkin_reminders,
        CronTrigger(
            hour=settings.SCHEDULER_CHECKIN_REMINDER_HOUR,
            minute=settings.SCHEDULER_CHECKIN_REMINDER_MINUTE,
            timezone=tz,
        ),
        id="checkin_reminders",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler iniciado")

    return _scheduler


def stop_scheduler():
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    _scheduler = None


def get_scheduler():
    return _scheduler
