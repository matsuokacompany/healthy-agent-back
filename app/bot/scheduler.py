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


async def send_prompt(bot_app, check_type: CheckTypeEnum) -> None:
    db = SessionLocal()
    users_processed = 0
    message = _build_message(check_type)

    try:
        users = db.query(User).filter(User.telegram_id.isnot(None)).all()

        if not users:
            logger.info("Nenhum usuário com telegram_id configurado para o prompt %s.", check_type.value)
            return

        for user in users:
            report = DailyReport(user_id=user.id, check_type=check_type)
            db.add(report)
            db.flush()

            user.current_report_id = report.id

            await bot_app.bot.send_message(chat_id=user.telegram_id, text=message)
            users_processed += 1

        db.commit()
        logger.info(
            "Prompt %s enviado com sucesso para %s usuário(s).",
            check_type.value,
            users_processed,
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Erro de banco ao enviar prompt %s.", check_type.value)
        raise
    except Exception:
        db.rollback()
        logger.exception("Erro ao enviar prompt %s pelo Telegram.", check_type.value)
        raise
    finally:
        db.close()


def start_scheduler(bot_app) -> AsyncIOScheduler:
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
        args=[bot_app, CheckTypeEnum.MORNING],
        id="telegram_morning_prompt",
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
        args=[bot_app, CheckTypeEnum.NIGHT],
        id="telegram_night_prompt",
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
