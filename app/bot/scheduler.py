from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone
from app.models.models import User
from app.db.session import SessionLocal

# Use AsyncIOScheduler, não BackgroundScheduler
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


async def send_daily_prompt(app):
    print("🚀 Executando send_daily_prompt")

    try:
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
    except Exception as e:
        print("❌ Erro no send_daily_prompt:", e)
    finally:
        db.close()


def schedule_daily_messages(app):
    # Verifica se o job já existe
    if scheduler.get_job("night_prompt"):
        return

    # Cria job
    scheduler.add_job(
        send_daily_prompt,
        CronTrigger(hour=22),  # envia às 22h horário do scheduler
        args=[app],
        id="night_prompt",
        replace_existing=True,
    )

    # Inicia scheduler
    if not scheduler.running:
        scheduler.start()