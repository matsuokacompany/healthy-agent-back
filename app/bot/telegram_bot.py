from telegram.ext import ApplicationBuilder
from app.bot.handlers.action_handler import register_action_handler
import asyncio
from app.bot.scheduler import schedule_prompts

def start_bot(token: str):
    """
    Inicializa o bot Telegram e retorna a aplicação.
    """
    app = ApplicationBuilder().token(token).build()
    register_action_handler(app)

    # Inicia o scheduler de prompts em background
    loop = asyncio.get_event_loop()
    loop.create_task(schedule_prompts(app))

    return app