from telegram.ext import ApplicationBuilder

from app.bot.channels.telegram_channel import TelegramBotChannel
from app.bot.handlers.action_handler import register_action_handler


def start_bot(token: str):
    """
    Inicializa o bot Telegram e retorna a aplicação.
    """
    app = ApplicationBuilder().token(token).build()
    telegram_channel = TelegramBotChannel(app)
    app.bot_data["telegram_channel"] = telegram_channel
    register_action_handler(app)
    return app
