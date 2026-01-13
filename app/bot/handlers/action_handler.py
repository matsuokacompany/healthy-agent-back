from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)
from app.db.session import SessionLocal
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository
from app.db.repositories.daily_log_repository import DailyLogRepository

ASK_SYMPTOM, ASK_ACTION = range(2)

NEGATIVE_ANSWERS = {"não", "nao", "n", "nenhum", "não tive", "nao tive"}


def get_repos():
    db = SessionLocal()
    return (
        db,
        UserRepository(db),
        SymptomRepository(db),
        DailyLogRepository(db),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Vou te ajudar a registrar seus sintomas diariamente.\n\n"
        "Teve algum sintoma hoje?"
    )
    return ASK_SYMPTOM


async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    nome = update.message.from_user.full_name
    text = update.message.text.strip().lower()

    db, user_repo, symptom_repo, log_repo = get_repos()

    try:
        user = user_repo.get_or_create_by_telegram_id(telegram_id, nome)

        if text in NEGATIVE_ANSWERS:
            log_repo.create_log(
                user_id=user.id,
                action="no_symptoms_reported"
            )

            await update.message.reply_text(
                "Perfeito 👍 Nenhum sintoma registrado hoje."
            )
            return ConversationHandler.END

        # Houve sintoma
        symptom_repo.create(user.id, text)

        log_repo.create_log(
            user_id=user.id,
            action="symptom_reported"
        )

        await update.message.reply_text(
            "Entendi. Agora me diga: o que você fez de diferente ontem?"
        )
        return ASK_ACTION

    finally:
        db.close()


async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    action_text = update.message.text.strip()

    db, user_repo, _, log_repo = get_repos()

    try:
        user = user_repo.get_user_by_telegram_id(telegram_id)

        if not user:
            await update.message.reply_text(
                "Não encontrei seu usuário. Use /start para iniciar novamente."
            )
            return ConversationHandler.END

        log_repo.create_log(
            user_id=user.id,
            action=f"action_reported: {action_text}"
        )

        await update.message.reply_text(
            "Perfeito! Suas informações foram registradas ✅"
        )
        return ConversationHandler.END

    finally:
        db.close()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registro cancelado 👍")
    return ConversationHandler.END


def register_action_handler(app):
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            # permite iniciar conversa mesmo após mensagem do scheduler
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_symptom),
        ],
        states={
            ASK_SYMPTOM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_symptom)
            ],
            ASK_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
