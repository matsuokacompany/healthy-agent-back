from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import SessionLocal
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository
from app.db.repositories.daily_log_repository import DailyLogRepository

ASK_ACTION = 1

NEGATIVE_ANSWERS = {"não", "nao", "n", "não tive", "nao tive", "nenhum"}

def get_repos():
    db = SessionLocal()
    return db, UserRepository(db), SymptomRepository(db), DailyLogRepository(db)


async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    nome = update.message.from_user.full_name
    text = update.message.text.strip().lower()

    db, user_repo, symptom_repo, daily_log_repo = get_repos()

    try:
        user = user_repo.get_or_create_by_telegram_id(telegram_id, nome)

        if text in NEGATIVE_ANSWERS:
            daily_log_repo.create_log(
                user_id=user.id,
                action="no_symptoms_reported"
            )

            await update.message.reply_text(
                "Perfeito 👍 Nenhum sintoma registrado hoje."
            )

            return ConversationHandler.END

        # Caso tenha sintomas
        symptom_repo.create(
            user_id=user.id,
            description=text
        )

        daily_log_repo.create_log(
            user_id=user.id,
            action="symptom_reported"
        )

        await update.message.reply_text(
            "Entendi. Agora me diga: o que você fez de diferente ontem?"
        )

        return ASK_ACTION

    finally:
        db.close()
