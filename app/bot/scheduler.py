from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone
import asyncio

from app.models.models import User
from app.db.session import SessionLocal

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


async def send_daily_prompt(app):
    db = SessionLocal()

    users = db.query(User).filter(User.telegram_id.isnot(None)).all()

    for user in users:
        await app.bot.send_message(
            chat_id=user.telegram_id,
            text="🌙 Boa noite! Teve algum sintoma hoje?"
        )

        user.awaiting_daily_response = True
        user.last_daily_prompt_at = datetime.now(timezone.utc)

    db.commit()
    db.close()


def schedule_daily_messages(app):
    if scheduler.running:
        return

    def job_wrapper():
        loop = asyncio.get_event_loop()
        loop.create_task(send_daily_prompt(app))

    scheduler.add_job(
        job_wrapper,
        CronTrigger(hour=22),
        id="night_prompt",
        replace_existing=True,
    )

    scheduler.start()
