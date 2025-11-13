from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import SessionLocal
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository
from app.db.repositories.daily_log_repository import DailyLogRepository

ASK_ACTION = 1

def get_repos():
    db = SessionLocal()
    return db, UserRepository(db), SymptomRepository(db), DailyLogRepository(db)

async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    nome = update.message.from_user.full_name
    text = update.message.text.strip()

    db, user_repo, symptom_repo, _ = get_repos()
    user = user_repo.get_or_create_by_telegram_id(telegram_id, nome)

    if text.lower() not in ["não", "nao"]:
        symptom_repo.create(user.id, text)
        await update.message.reply_text("Entendi! Agora me diga: o que você fez de diferente ontem?")
        db.close()
        return ASK_ACTION
    else:
        await update.message.reply_text("Beleza, sem sintomas registrados hoje. 👍")
        db.close()
        return ConversationHandler.END
