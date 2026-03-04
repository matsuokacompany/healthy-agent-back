from sqlalchemy import func
from app.models.models import User, TelegramLinkCode
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
    return db, UserRepository(db), SymptomRepository(db), DailyLogRepository(db)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == context.bot.id:
        return ConversationHandler.END

    args = context.args
    if not args:
        await update.message.reply_text("Envie /start SEU_CODIGO para vincular sua conta.")
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

        await update.message.reply_text("Conta vinculada com sucesso ✅")
        return ConversationHandler.END

    finally:
        db.close()

async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == context.bot.id:
        return ConversationHandler.END

    telegram_id = str(update.message.from_user.id)
    text = update.message.text.strip().lower()
    db, user_repo, symptom_repo, log_repo = get_repos()

    try:
        user = user_repo.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text("Sua conta não está vinculada. Use /start SEU_CODIGO.")
            return ConversationHandler.END

        if text in NEGATIVE_ANSWERS:
            log_repo.create_log(user_id=user.id, action="no_symptoms_reported")
            await update.message.reply_text("Perfeito 👍 Nenhum sintoma registrado hoje.")
            return ConversationHandler.END

        symptom_repo.create(user.id, text)
        log_repo.create_log(user_id=user.id, action="symptom_reported")
        await update.message.reply_text("Entendi. Agora me diga: o que você fez de diferente ontem?")
        return ASK_ACTION

    finally:
        db.close()

async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == context.bot.id:
        return ConversationHandler.END

    telegram_id = str(update.message.from_user.id)
    action_text = update.message.text.strip()
    db, user_repo, _, log_repo = get_repos()

    try:
        user = user_repo.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text("Não encontrei seu usuário. Use /start para iniciar novamente.")
            return ConversationHandler.END

        log_repo.create_log(user_id=user.id, action=f"action_reported: {action_text}")
        await update.message.reply_text("Perfeito! Suas informações foram registradas ✅")
        return ConversationHandler.END

    finally:
        db.close()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registro cancelado 👍")
    return ConversationHandler.END

def register_action_handler(app):
    print("ASK_SYMPTOM FOI CHAMADO")
    print("Mensagem recebida:", text)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, ask_symptom)
    )