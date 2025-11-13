from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters
from app.db.session import SessionLocal
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.symptom_repository import SymptomRepository
from app.db.repositories.daily_log_repository import DailyLogRepository

# Estados da conversa
ASK_SYMPTOM, ASK_ACTION = range(2)


# ==========================
# 🔹 Função auxiliar
# ==========================
def get_repos():
    db = SessionLocal()
    user_repo = UserRepository(db)
    symptom_repo = SymptomRepository(db)
    log_repo = DailyLogRepository(db)
    return db, user_repo, symptom_repo, log_repo


# ==========================
# 🔹 Fluxo da conversa
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Início da conversa"""
    await update.message.reply_text("Olá! Vou te ajudar a registrar seus sintomas diariamente 😊")
    await update.message.reply_text("Teve algum sintoma hoje?")
    return ASK_SYMPTOM


async def ask_symptom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pergunta sobre sintomas"""
    telegram_id = str(update.message.from_user.id)
    nome = update.message.from_user.full_name
    text = update.message.text.strip()

    db, user_repo, symptom_repo, log_repo = get_repos()

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


async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pergunta sobre atividades do dia anterior"""
    telegram_id = str(update.message.from_user.id)
    text = update.message.text.strip()

    db, user_repo, symptom_repo, log_repo = get_repos()
    user = user_repo.get_user_by_telegram_id(telegram_id)
    if user:
        log_repo.create_log(user.id, text)
        await update.message.reply_text("Perfeito! Suas informações foram registradas ✅")
    else:
        await update.message.reply_text("Erro: usuário não encontrado. Tente iniciar com /start novamente.")
    db.close()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o registro"""
    await update.message.reply_text("Registro cancelado. 👍")
    return ConversationHandler.END


# ==========================
# 🔹 Função de registro
# ==========================
def register_action_handler(app):
    """Adiciona o handler de conversa ao bot"""
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_SYMPTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_symptom)],
            ASK_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv_handler)
