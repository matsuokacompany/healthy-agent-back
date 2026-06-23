import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import CheckTypeEnum, User

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


# =========================================================
# MESSAGE BUILDER
# =========================================================

def _build_message(check_type: CheckTypeEnum) -> str:
    if check_type == CheckTypeEnum.MORNING:
        return (
            "🌅 Bom dia!\n"
            "Você teve algum sintoma indesejado antes de dormir ou enquanto dormia?"
        )

    return (
        "🌙 Boa noite!\n"
        "Você teve algum sintoma indesejado durante o dia?"
    )


# =========================================================
# CORE JOB (CORRIGIDO)
# =========================================================

async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:
    logger.info("SEND_PROMPT START | type=%s", check_type.value)

    message = _build_message(check_type)

    db = SessionLocal()

    users_processed = 0
    users_failed = 0

    try:
        users = db.query(User).all()

        logger.info("USERS FOUND=%s", len(users))

        for user in users:
            try:
                channel = bot_manager.get_channel_for_user(user)

                if not channel:
                    logger.warning(
                        "NO CHANNEL | user_id=%s",
                        user.id,
                    )
                    continue

                destination = user.phone

                logger.info(
                    "SENDING PROMPT | user_id=%s | phone=%s",
                    user.id,
                    destination,
                )

                # 🔥 IMPORTANTE:
                # scheduler NÃO cria estado mais
                await channel.send_message(destination, message)

                users_processed += 1

                logger.info(
                    "SENT OK | user_id=%s",
                    user.id,
                )

            except Exception:
                users_failed += 1
                logger.exception(
                    "ERROR SENDING PROMPT | user_id=%s",
                    user.id,
                )

        db.commit()

    finally:
        db.close()

    logger.info(
        "SEND_PROMPT DONE | type=%s | sent=%s | failed=%s",
        check_type.value,
        users_processed,
        users_failed,
    )


# =========================================================
# SCHEDULER CONTROL
# =========================================================

def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def start_scheduler(bot_manager) -> AsyncIOScheduler:
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Scheduler já em execução.")
        return _scheduler

    timezone = ZoneInfo(settings.SCHEDULER_TIMEZONE)

    _scheduler = AsyncIOScheduler(
        timezone=timezone,
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
            timezone=timezone,
        ),
        args=[bot_manager, CheckTypeEnum.MORNING],
        id="bot_morning_prompt",
        replace_existing=True,
    )

    _scheduler.add_job(
        send_prompt,
        CronTrigger(
            hour=settings.SCHEDULER_NIGHT_HOUR,
            minute=settings.SCHEDULER_NIGHT_MINUTE,
            timezone=timezone,
        ),
        args=[bot_manager, CheckTypeEnum.NIGHT],
        id="bot_night_prompt",
        replace_existing=True,
    )

    _scheduler.start()

    logger.info(
        "Scheduler iniciado | TZ=%s | morning=%02d:%02d | night=%02d:%02d",
        settings.SCHEDULER_TIMEZONE,
        settings.SCHEDULER_MORNING_HOUR,
        settings.SCHEDULER_MORNING_MINUTE,
        settings.SCHEDULER_NIGHT_HOUR,
        settings.SCHEDULER_NIGHT_MINUTE,
    )

    return _scheduler


def stop_scheduler() -> None:
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler finalizado.")

    _scheduler = None