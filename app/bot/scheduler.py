from apscheduler.schedulers.background import BackgroundScheduler
from app.db.session import SessionLocal
from app.models.models import User

async def send_message(app, text):
    db = SessionLocal()
    users = db.query(User).filter(User.telegram_id.isnot(None)).all()
    db.close()

    for user in users:
        await app.bot.send_message(chat_id=user.telegram_id, text=text)

def schedule_daily_messages(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: send_message(app, "☀️ Bom dia! Teve algum sintoma hoje?"), 'cron', hour=8)
    scheduler.add_job(lambda: send_message(app, "🌙 Boa noite! Teve algum sintoma hoje?"), 'cron', hour=20)
    scheduler.start()
