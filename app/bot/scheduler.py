from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.models.models import User
from app.db.session import SessionLocal

scheduler = AsyncIOScheduler(timezone=ZoneInfo("America/Sao_Paulo"))


async def send_daily_prompt(app):
    db = SessionLocal()
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime.now(tz)
    today = now.date()

    try:
        users = db.query(User).filter(User.telegram_id.isnot(None)).all()

        for user in users:
            if user.last_daily_prompt_at:
                last_date = user.last_daily_prompt_at.astimezone(tz).date()
                if last_date == today:
                    continue

            try:
                await app.bot.send_message(
                    chat_id=user.telegram_id,
                    text="🌙 Boa noite! Teve algum sintoma hoje?"
                )
            except Exception as e:
                print(f"Erro ao enviar mensagem para {user.id}: {e}")

            user.awaiting_daily_response = True
            user.last_daily_prompt_at = now

        db.commit()

    finally:
        db.close()


def schedule_daily_messages(app):

    async def job():
        await send_daily_prompt(app)

    if not scheduler.get_job("night_prompt"):
        scheduler.add_job(
            job,
            trigger=CronTrigger(
                minute="*/1",
                timezone=ZoneInfo("America/Sao_Paulo"),
            ),
            id="night_prompt",
            replace_existing=True,
        )

    if not scheduler.running:
        scheduler.start()