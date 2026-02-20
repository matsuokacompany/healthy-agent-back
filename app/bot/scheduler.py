import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.models.models import User
from app.db.session import SessionLocal

# Scheduler com timezone local
scheduler = BackgroundScheduler(timezone=ZoneInfo("America/Sao_Paulo"))

async def send_daily_prompt(app):
    print(f"🚀 Executando send_daily_prompt: {datetime.now(ZoneInfo('America/Sao_Paulo'))}")

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.telegram_id.isnot(None)).all()

        for user in users:
            # Evita enviar mais de uma vez por dia
            if user.last_daily_prompt_at and user.last_daily_prompt_at.date() == datetime.now(timezone.utc).date():
                continue

            try:
                await app.bot.send_message(
                    chat_id=user.telegram_id,
                    text="🌙 Boa noite! Teve algum sintoma hoje?"
                )
            except Exception as e:
                print(f"❌ Erro ao enviar mensagem para {user.id}: {e}")

            user.awaiting_daily_response = True
            user.last_daily_prompt_at = datetime.now(timezone.utc)

        db.commit()

    except Exception as e:
        print(f"❌ Erro no send_daily_prompt: {e}")

    finally:
        db.close()


def schedule_daily_messages(app):
    # Evita duplicação de jobs ao reiniciar o container
    if scheduler.get_job("night_prompt"):
        print("Job 'night_prompt' já agendado ✅")
    else:
        async def job():
            await send_daily_prompt(app)

        def wrapper():
            asyncio.create_task(job())

        scheduler.add_job(
            wrapper,
            trigger=CronTrigger(hour=22, minute=0),  # Sempre 22:00 horário São Paulo
            id="night_prompt",
            replace_existing=True,
        )
        print("Job 'night_prompt' agendado ✅")

    # Inicia scheduler se ainda não estiver rodando
    if not scheduler.running:
        scheduler.start()
        print("Scheduler iniciado ✅")

    print("Jobs agendados:", scheduler.get_jobs())