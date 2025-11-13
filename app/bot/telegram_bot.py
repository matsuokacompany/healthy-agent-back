import logging
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler
)
from app.bot.handlers import (
    start_handler, symptom_handler, action_handler, report_handler
)
from app.bot.scheduler import schedule_daily_messages
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
TOKEN = settings.TELEGRAM_BOT_TOKEN

ASK_SYMPTOM, ASK_ACTION = range(2)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Conversa principal
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler.start)],
        states={
            ASK_SYMPTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, symptom_handler.ask_symptom)],
            ASK_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, action_handler.ask_action)],
        },
        fallbacks=[CommandHandler("cancel", start_handler.cancel)],
    )

    # Comandos adicionais
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("relatorio_semanal", report_handler.relatorio_semanal))
    app.add_handler(CommandHandler("relatorio_mensal", report_handler.relatorio_mensal))

    # Agendador
    schedule_daily_messages(app)

    print("🤖 Bot Telegram rodando e pronto para uso...")
    app.run_polling()

if __name__ == "__main__":
    main()
