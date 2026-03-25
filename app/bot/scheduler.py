import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import CheckTypeEnum, DailyReport, User

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


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
    db = SessionLocal()
    users_processed = 0
    users_failed = 0
    message = _build_message(check_type)

    try:
        users = db.query(User).all()

        if not users:
            logger.info("Nenhum usuário encontrado para o prompt %s.", check_type.value)
            return

        for user in users:
            try:
                channel_name = bot_manager.resolve_channel_name_for_user(user)
                channel = bot_manager.get_channel_for_user(user)
                if not channel_name or not channel:
                    logger.info("Usuário sem canal elegível para prompt. user_id=%s", user.id)
                    continue

                if channel_name == "whatsapp":
                    logger.info(
                        "Prompt não enviado para WhatsApp por segurança (stub). user_id=%s",
                        user.id,
                    )
                    continue

                target_user_id = user.telegram_id
                if not target_user_id:
                    logger.warning("Usuário sem identificador válido no canal %s. user_id=%s", channel_name, user.id)
                    continue

                report = DailyReport(user_id=user.id, check_type=check_type)
                db.add(report)
                db.flush()
                user.current_report_id = report.id

                await channel.send_message(target_user_id, message)
                db.commit()
                users_processed += 1
                logger.info(
                    "Prompt enviado com sucesso. check_type=%s user_id=%s channel=%s report_id=%s",
                    check_type.value,
                    user.id,
                    channel_name,
                    report.id,
                )
            except SQLAlchemyError:
                db.rollback()
                users_failed += 1
                logger.exception(
                    "Erro de banco ao enviar prompt individual. check_type=%s user_id=%s",
                    check_type.value,
                    user.id,
                )
            except Exception:
                db.rollback()
                users_failed += 1
                logger.exception(
                    "Erro no envio de prompt individual. check_type=%s user_id=%s",
                    check_type.value,
                    user.id,
                )

        logger.info(
            "Envio de prompt finalizado. check_type=%s enviados=%s falhas=%s",
            check_type.value,
            users_processed,
            users_failed,
        )
    finally:
        db.close()


def start_scheduler(bot_manager) -> AsyncIOScheduler:
    global scheduler

    if scheduler and scheduler.running:
        logger.info("Scheduler já está em execução; reutilizando instância existente.")
        return scheduler

    timezone = ZoneInfo(settings.SCHEDULER_TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=timezone)

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
        misfire_grace_time=1800,
        coalesce=True,
        max_instances=1,
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
        misfire_grace_time=1800,
        coalesce=True,
        max_instances=1,
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


def stop_scheduler() -> None:
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler finalizado com sucesso.")

    scheduler = None
