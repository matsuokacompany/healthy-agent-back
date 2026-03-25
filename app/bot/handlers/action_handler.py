import logging

from sqlalchemy import func
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.db.session import SessionLocal
from app.models.models import TelegramLinkCode, User

logger = logging.getLogger(__name__)

ASK_CAUSE, = range(1)


# ========================= /start =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Envie /start SEU_CODIGO para vincular sua conta."
        )
        return ConversationHandler.END

    code = args[0]
    telegram_id = str(update.message.from_user.id)
    db = SessionLocal()
    try:
        link = db.query(TelegramLinkCode).filter(
            TelegramLinkCode.code == code,
            TelegramLinkCode.used == False,
            TelegramLinkCode.expires_at > func.now()
        ).first()

        if not link:
            await update.message.reply_text("Código inválido ou expirado.")
            return ConversationHandler.END

        user = db.query(User).filter(User.id == link.user_id).first()
        if not user:
            await update.message.reply_text("Usuário não encontrado.")
            return ConversationHandler.END

        user.telegram_id = telegram_id
        link.used = True
        db.commit()

        logger.info("Conta vinculada via Telegram. user_id=%s telegram_id=%s", user.id, telegram_id)
        await update.message.reply_text("Conta vinculada com sucesso ✅")
        return ConversationHandler.END

    finally:
        db.close()


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        logger.warning("Update Telegram sem mensagem/from_user ignorado.")
        return ConversationHandler.END

    telegram_channel = context.application.bot_data.get("telegram_channel")
    if not telegram_channel:
        logger.error("Telegram channel não configurado no bot_data.")
        await update.message.reply_text("Canal indisponível no momento. Tente novamente.")
        return ConversationHandler.END

    response = await telegram_channel.handle_incoming(
        {
            "user_id": str(update.message.from_user.id),
            "text": (update.message.text or "").strip(),
            "reply": update.message.reply_text,
        }
    )

    if response and response.ask_followup:
        return ASK_CAUSE

    return ConversationHandler.END


# ====================== Pergunta sobre sintomas ======================
async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _handle_text(update, context)


# ====================== Pergunta sobre ação ======================
async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _handle_text(update, context)


# ====================== /cancel ======================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registro cancelado 👍")
    return ConversationHandler.END


# ====================== Registro do ConversationHandler ======================
def register_action_handler(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_symptom)
        ],
        states={
            ASK_CAUSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
