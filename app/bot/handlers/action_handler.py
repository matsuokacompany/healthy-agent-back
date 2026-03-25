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
    raw_text = (update.message.text if update and update.message else "") or ""
    from_user = update.message.from_user.id if update and update.message and update.message.from_user else None
    logger.info(
        "Entrada de mensagem no handler Telegram. from_user=%s chars=%s text_preview=%s",
        from_user,
        len(raw_text),
        raw_text[:80],
    )

    if not update.message or not update.message.from_user:
        logger.warning("Update Telegram sem message/from_user. update=%s", update)
        return ConversationHandler.END

    telegram_channel = context.application.bot_data.get("telegram_channel")
    if not telegram_channel:
        logger.error("Telegram channel não configurado no bot_data.")
        await update.message.reply_text("Canal indisponível no momento. Tente novamente.")
        return ConversationHandler.END

    try:
        response = await telegram_channel.handle_incoming(
            {
                "user_id": str(update.message.from_user.id),
                "text": raw_text.strip(),
                "reply": update.message.reply_text,
            }
        )
    except Exception:
        logger.exception("Falha ao delegar mensagem para TelegramBotChannel.")
        await update.message.reply_text("Ocorreu um erro ao processar sua resposta. Tente novamente.")
        return ConversationHandler.END

    if response and response.ask_followup:
        logger.info("Fluxo Telegram seguirá para ASK_CAUSE. from_user=%s", from_user)
        return ASK_CAUSE

    logger.info("Fluxo Telegram encerrado para mensagem atual. from_user=%s", from_user)
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
    logger.info("ConversationHandler do Telegram registrado com sucesso.")
