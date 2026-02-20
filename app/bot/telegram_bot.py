from telegram.ext import ApplicationBuilder
from app.bot.handlers.action_handler import register_action_handler

def start_bot(token: str):
    app = ApplicationBuilder().token(token).build()

    register_action_handler(app)

    return app
