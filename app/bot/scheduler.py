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
# CORE JOB
# =========================================================

async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:
    logger.info("🚀 SEND_PROMPT START | type=%s", check_type.value)

    message = _build_message(check_type)

    users_processed = 0
    users_failed = 0

    db = SessionLocal()

    try:
        users = db.query(User).all()

        logger.info("🔎 USERS FOUND=%s", len(users))

        if not users:
            logger.warning(
                "⚠️ Nenhum usuário encontrado para prompt | type=%s",
                check_type.value,
            )
            return

        for user in users:
            try:
                logger.info("➡️ PROCESSING user_id=%s", user.id)

                channel_name = bot_manager.resolve_channel_name_for_user(user)
                channel = bot_manager.get_channel_for_user(user)

                logger.info(
                    "📡 CHANNEL RESOLUTION | user_id=%s | channel=%s | available=%s",
                    user.id,
                    channel_name,
                    bool(channel),
                )

                if not channel_name or not channel:
                    logger.warning(
                        "❌ Usuário sem canal válido | user_id=%s",
                        user.id,
                    )
                    continue

                now = datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE))

                user.pending_check_type = check_type
                user.pending_report_date = now.date()
                user.pending_prompt_sent_at = now

                destination = (
                    user.telegram_id
                    if channel_name == "telegram"
                    else user.phone
                )

                logger.info(
                    "📤 SENDING MESSAGE | user_id=%s | destination=%s",
                    user.id,
                    destination,
                )

                await channel.send_message(destination, message)

                db.add(user)
                users_processed += 1

                logger.info(
                    "✅ SENT SUCCESS | user_id=%s | type=%s",
                    user.id,
                    check_type.value,
                )

            except SQLAlchemyError:
                db.rollback()
                users_failed += 1
                logger.exception(
                    "🧨 SQL ERROR | user_id=%s",
                    user.id,
                )

            except Exception:
                db.rollback()
                users_failed += 1
                logger.exception(
                    "🔥 GENERAL ERROR | user_id=%s",
                    user.id,
                )

        # 💡 commit único (melhor performance e consistência)
        db.commit()

    finally:
        db.close()

    logger.info(
        "🏁 SEND_PROMPT DONE | type=%s | sent=%s | failed=%s",
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
        logger.info("Scheduler já está em execução; reutilizando instância existente.")
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
        id="bot_morning_prompt",
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
        id="bot_night_prompt",
        replace_existing=True,
    )

    scheduler.start()

    logger.info(
        "Scheduler iniciado no timezone %s. Manhã: %02d:%02d | Noite: %02d:%02d",
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

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler finalizado com sucesso.")

    scheduler = None