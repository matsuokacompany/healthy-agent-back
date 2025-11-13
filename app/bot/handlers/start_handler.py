from telegram import Update
from telegram.ext import ContextTypes

ASK_SYMPTOM = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! 👋 Vou te ajudar a registrar seus sintomas diariamente.")
    await update.message.reply_text("Teve algum sintoma hoje?")
    return ASK_SYMPTOM

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registro cancelado. 👍")
    return ConversationHandler.END
