import logging
import os
import sys

from fastapi import FastAPI

from app.bot.channels.bot_manager import BotManager
from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
from app.bot.scheduler import start_scheduler, stop_scheduler
from app.bot.telegram_bot import start_bot, start_telegram_polling, stop_telegram_polling
from app.routes import (
    anamnese_routes,
    auth_routes,
    bot_webhook_routes,
    daily_reports_routes,
    insight_routes,
    report_routes,
    user_routes,
)

# ===============================
# Configurações de logging
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

ENV = os.getenv("ENV", "dev").lower()
DEBUG = ENV == "dev"

# ===============================
# Inicializa FastAPI
# ===============================
app = FastAPI(
    title="Symptom Tracker API",
    redirect_slashes=False,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
)

API_PREFIX = "/api"

# ===============================
# Inclui rotas
# ===============================
app.include_router(auth_routes.router, prefix=f"{API_PREFIX}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API_PREFIX}/anamneses")
app.include_router(daily_reports_routes.router, prefix=f"{API_PREFIX}/daily-reports")
app.include_router(insight_routes.router, prefix=f"{API_PREFIX}/insights")
app.include_router(report_routes.router, prefix=f"{API_PREFIX}/reports")
app.include_router(user_routes.router, prefix=f"{API_PREFIX}/users")
app.include_router(bot_webhook_routes.router)

# ===============================
# Bot Telegram / WhatsApp
# ===============================
telegram_app = None


@app.on_event("startup")
async def startup_event():
    global telegram_app
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

    bot_manager = BotManager()
    bot_manager.register_channel("whatsapp", WhatsAppBotChannel())
    app.state.bot_manager = bot_manager

    if not telegram_token:
        logger.warning("TELEGRAM_BOT_TOKEN não definido. Bot Telegram não será iniciado.")
        return

    try:
        telegram_app = start_bot(telegram_token)
        await start_telegram_polling(telegram_app)

        telegram_channel = telegram_app.bot_data.get("telegram_channel")
        if telegram_channel:
            bot_manager.register_channel("telegram", telegram_channel)
            logger.info("Canal Telegram registrado no BotManager.")
        else:
            logger.error("Telegram channel ausente no bot_data após inicialização.")

        start_scheduler(bot_manager)
        logger.info("Scheduler iniciado com BotManager.")
    except Exception:
        logger.exception("Falha ao inicializar bot Telegram; API seguirá ativa sem polling.")


@app.on_event("shutdown")
async def shutdown_event():
    global telegram_app

    stop_scheduler()

    if telegram_app:
        await stop_telegram_polling(telegram_app)
