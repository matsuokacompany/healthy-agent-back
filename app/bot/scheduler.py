import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import or_

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import CheckTypeEnum, MonitoringPlan, User
from app.services.daily_report_service import DailyReportService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:
    logger.info("SEND_PROMPT START | type=%s", check_type.value)

    db = SessionLocal()
    plans_processed = 0
    plans_skipped = 0
    plans_failed = 0

    try:
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

                await channel.send_template(
                    user=user,
                    check_type=check_type,
                    report_date=report.report_date,
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
        db.close()

    logger.info(
        "SEND_PROMPT DONE | sent=%s skipped=%s failed=%s",
        plans_processed,
        plans_skipped,
        plans_failed,
    )


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
