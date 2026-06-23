import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import CheckTypeEnum, User

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


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


async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:

    logger.info("SEND_PROMPT START | type=%s", check_type.value)

    message = _build_message(check_type)

    db = SessionLocal()

    users_processed = 0
    users_failed = 0

    try:
        users = db.query(User).all()

        for user in users:
            try:
                channel = bot_manager.get_channel_for_user(user)

                if not channel or not user.phone:
                    continue

                # 🔥 CORRETO: só abre uma NOVA janela de resposta
                # não destrói histórico ativo imediatamente

                user.pending_check_type = check_type
                user.pending_report_date = None
                user.pending_prompt_sent_at = user.pending_prompt_sent_at or None

                # ⚠️ IMPORTANTE:
                # NÃO mexer em current_report_id aqui

                await channel.send_message(user.phone, message)

                users_processed += 1

            except Exception:
                users_failed += 1
                logger.exception("ERROR user_id=%s", user.id)

        db.commit()

    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_prompt")

    finally:
        db.close()

    logger.info(
        "SEND_PROMPT DONE | sent=%s failed=%s",
        users_processed,
        users_failed,
    )


def get_scheduler():
    return _scheduler


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
        send_prompt,
        CronTrigger(
            hour=settings.SCHEDULER_NIGHT_HOUR,
            minute=settings.SCHEDULER_NIGHT_MINUTE,
            timezone=tz,
        ),
        args=[bot_manager, CheckTypeEnum.NIGHT],
        id="night",
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