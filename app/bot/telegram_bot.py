import logging

from telegram import Update
from telegram.ext import ApplicationBuilder

from app.bot.channels.telegram_channel import TelegramBotChannel
from app.bot.handlers.action_handler import register_action_handler

logger = logging.getLogger(__name__)


def start_bot(token: str):
    """Inicializa estrutura do bot Telegram e registra handlers."""
    app = ApplicationBuilder().token(token).build()
    telegram_channel = TelegramBotChannel(app)
    app.bot_data["telegram_channel"] = telegram_channel
    register_action_handler(app)
    logger.info("Bot Telegram criado com handlers registrados.")
    return app


async def start_telegram_polling(app) -> None:
    """Inicialização compatível com python-telegram-bot v20+."""
    updater = getattr(app, "updater", None)
    if updater is None:
        raise RuntimeError("Application sem updater; não foi possível iniciar polling do Telegram.")

    await app.initialize()
    await updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await app.start()
    logger.info("Polling do Telegram iniciado com sucesso.")


async def stop_telegram_polling(app) -> None:
    updater = getattr(app, "updater", None)
    if updater and updater.running:
        await updater.stop()
        logger.info("Polling do Telegram interrompido.")

    await app.stop()
    await app.shutdown()
    logger.info("Aplicação Telegram finalizada com sucesso.")
