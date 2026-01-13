from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

from app.models.models import User
from app.db.session import SessionLocal

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


async def send_daily_prompt(app, text: str):
    db = SessionLocal()
    users = db.query(User).filter(User.telegram_id.isnot(None)).all()
    db.close()

    for user in users:
        await app.bot.send_message(
            chat_id=user.telegram_id,
            text=text
        )


def schedule_daily_messages(app):
    if scheduler.running:
        return

    def job_wrapper(text: str):
        asyncio.run(send_daily_prompt(app, text))

    scheduler.add_job(
        job_wrapper,
        CronTrigger(hour=10),
        args=["☀️ Bom dia! Você teve algum sintoma desde ontem à noite?"],
        id="morning_prompt",
        replace_existing=True,
    )

    scheduler.add_job(
        job_wrapper,
        CronTrigger(hour=18),
        args=["🌤️ Boa tarde! Teve algum sintoma ao longo do dia?"],
        id="afternoon_prompt",
        replace_existing=True,
    )

    scheduler.add_job(
        job_wrapper,
        CronTrigger(hour=22),
        args=["🌙 Boa noite! Teve algum sintoma hoje?"],
        id="night_prompt",
        replace_existing=True,
    )

    scheduler.start()
