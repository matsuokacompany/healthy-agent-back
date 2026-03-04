from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import SessionLocal
from app.db.repositories.user_repository import UserRepository
from app.services.symptom_service import SymptomService

ASK_ACTION = 1


async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    nome = update.message.from_user.full_name
    text = update.message.text.strip()

    db = SessionLocal()

    try:
        user_repo = UserRepository(db)
        user = user_repo.get_or_create_by_telegram_id(telegram_id, nome)

        result = SymptomService.process_daily_response(
            db=db,
            user=user,
            message=text
        )

        if result == "NOT_AWAITING":
            await update.message.reply_text(
                "Você não possui um registro pendente hoje."
            )
            return ConversationHandler.END

        if result == "EXPIRED":
            await update.message.reply_text(
                "O tempo para responder expirou."
            )
            return ConversationHandler.END

        if result == "NEGATIVE":
            await update.message.reply_text(
                "Perfeito 👍 Nenhum sintoma registrado hoje."
            )
            return ConversationHandler.END

        if result == "SAVED":
            await update.message.reply_text(
                "Entendi. Agora me diga: o que você fez de diferente ontem?"
            )
            return ASK_ACTION

        # fallback defensivo
        await update.message.reply_text(
            "Ocorreu um erro inesperado."
        )
        return ConversationHandler.END

    finally:
        db.close()