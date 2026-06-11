import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import CheckTypeEnum, User

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


# =========================================================
# MESSAGE BUILDER
# =========================================================

def build_message(check_type: CheckTypeEnum) -> str:
    if check_type == CheckTypeEnum.MORNING:
        return (
            "🌅 Bom dia!\n"
            "Você teve algum sintoma indesejado antes de dormir ou durante a noite?"
        )

    return (
        "🌙 Boa noite!\n"
        "Você teve algum sintoma indesejado durante o dia?"
    )


# =========================================================
# CORE JOB
# =========================================================

async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:
    message = build_message(check_type)

    users_processed = 0
    users_failed = 0

    db = SessionLocal()

    try:
        users = db.query(User).all()

        if not users:
            logger.warning("Nenhum usuário encontrado para prompt: %s", check_type.value)
            return

        for user in users:
            try:
                channel_name = bot_manager.resolve_channel_name_for_user(user)
                channel = bot_manager.get_channel_for_user(user)

                if not channel_name or not channel:
                    logger.debug("Usuário sem canal válido. user_id=%s", user.id)
                    continue

                # WhatsApp ainda é stub
                if channel_name == "whatsapp":
                    logger.info("WhatsApp ainda em modo stub. user_id=%s", user.id)
                    continue

                if not user.telegram_id:
                    logger.warning("Usuário sem telegram_id. user_id=%s", user.id)
                    continue

                now = datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE))

                user.pending_check_type = check_type
                user.pending_report_date = now.date()
                user.pending_prompt_sent_at = now

                await channel.send_message(user.telegram_id, message)

                db.add(user)
                db.commit()

                users_processed += 1

                logger.info(
                    "Prompt enviado com sucesso | user_id=%s | type=%s",
                    user.id,
                    check_type.value,
                )

            except SQLAlchemyError:
                db.rollback()
                users_failed += 1
                logger.exception("Erro SQL no envio de prompt | user_id=%s", user.id)

            except Exception:
                db.rollback()
                users_failed += 1
                logger.exception("Erro geral no envio de prompt | user_id=%s", user.id)

    finally:
        db.close()

    logger.info(
        "JOB FINALIZADO | type=%s | enviados=%s | falhas=%s",
        check_type.value,
        users_processed,
        users_failed,
    )


# =========================================================
# SCHEDULER START
# =========================================================

def start_scheduler(bot_manager) -> AsyncIOScheduler:
    global scheduler

    if scheduler and scheduler.running:
        logger.warning("Scheduler já estava rodando — evitando duplicação.")
        return scheduler

    timezone = ZoneInfo(settings.SCHEDULER_TIMEZONE)

    scheduler = AsyncIOScheduler(
        timezone=timezone,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 1800,
        },
    )

    scheduler.add_job(
        send_prompt,
        CronTrigger(
            hour=settings.SCHEDULER_MORNING_HOUR,
            minute=settings.SCHEDULER_MORNING_MINUTE,
            timezone=timezone,
        ),
        args=[bot_manager, CheckTypeEnum.MORNING],
        id="morning_prompt",
        replace_existing=True,
    )

    scheduler.add_job(
        send_prompt,
        CronTrigger(
            hour=settings.SCHEDULER_NIGHT_HOUR,
            minute=settings.SCHEDULER_NIGHT_MINUTE,
            timezone=timezone,
        ),
        args=[bot_manager, CheckTypeEnum.NIGHT],
        id="night_prompt",
        replace_existing=True,
    )

    scheduler.start()

    logger.info(
        "Scheduler ativo | TZ=%s | manhã=%02d:%02d | noite=%02d:%02d",
        settings.SCHEDULER_TIMEZONE,
        settings.SCHEDULER_MORNING_HOUR,
        settings.SCHEDULER_MORNING_MINUTE,
        settings.SCHEDULER_NIGHT_HOUR,
        settings.SCHEDULER_NIGHT_MINUTE,
    )

    return scheduler


# =========================================================
# STOP
# =========================================================

def stop_scheduler() -> None:
    global scheduler

    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler desligado.")

    scheduler = None