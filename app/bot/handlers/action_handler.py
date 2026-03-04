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
from app.db.repositories.daily_repository import DailyRepository  # ✅ novo

ASK_SYMPTOM, ASK_ACTION = range(2)

NEGATIVE_ANSWERS = {"não", "nao", "n", "nenhum", "não tive", "nao tive"}


def get_repos():
    """Retorna instâncias de repositórios com sessão do DB"""
    db = SessionLocal()
    return db, UserRepository(db), SymptomRepository(db), DailyRepository(db)


# ============================================================
#                       /start
# ============================================================
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

        await update.message.reply_text("Conta vinculada com sucesso ✅")
        return ConversationHandler.END

    finally:
        db.close()


# ============================================================
#                  Pergunta sobre sintomas
# ============================================================
async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    text = update.message.text.strip().lower()
    db, user_repo, symptom_repo, daily_repo = get_repos()

    try:
        user = user_repo.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text(
                "Sua conta não está vinculada. Use /start SEU_CODIGO."
            )
            return ConversationHandler.END

        if not daily_repo.is_awaiting(user):
            await update.message.reply_text(
                "Você não possui um registro pendente hoje."
            )
            return ConversationHandler.END

        if text in NEGATIVE_ANSWERS:
            daily_repo.mark_response_received(user)
            await update.message.reply_text("Perfeito 👍 Nenhum sintoma registrado hoje.")
            return ConversationHandler.END

        # Salva sintoma
        symptom_repo.create(user.id, text)

        await update.message.reply_text(
            "Entendi. Agora me diga: o que você fez de diferente ontem? "
            "(tente descrever algo que possa ter causado o sintoma)"
        )

        return ASK_ACTION

    finally:
        db.close()


# ============================================================
#                  Pergunta sobre ação
# ============================================================
async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    action_text = update.message.text.strip()
    db, user_repo, symptom_repo, daily_repo = get_repos()

    try:
        user = user_repo.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text(
                "Não encontrei seu usuário. Use /start para iniciar novamente."
            )
            return ConversationHandler.END

        # Opcional: salvar ação como sintoma contextual
        # symptom_repo.create(user.id, f"AÇÃO: {action_text}")

        # Marca que o usuário respondeu
        daily_repo.mark_response_received(user)

        await update.message.reply_text(
            "Perfeito! Suas informações foram registradas ✅"
        )

        return ConversationHandler.END

    finally:
        db.close()


# ============================================================
#                       /cancel
# ============================================================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registro cancelado 👍")
    return ConversationHandler.END


# ============================================================
#               Registro do ConversationHandler
# ============================================================
def register_action_handler(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_symptom)
        ],
        states={
            ASK_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)