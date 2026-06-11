import logging
import os
import sys
from contextlib import asynccontextmanager

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
# LOGGING
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

ENV = os.getenv("ENV", "dev").lower()
DEBUG = ENV == "dev"

telegram_app = None


# ===============================
# LIFESPAN (STARTUP + SHUTDOWN)
# ===============================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    # ======================
    # STARTUP
    # ======================
    bot_manager = BotManager()

    # WhatsApp sempre ativo
    bot_manager.register_channel("whatsapp", WhatsAppBotChannel())
    app.state.bot_manager = bot_manager

    # Scheduler sempre ativo (independente de Telegram)
    start_scheduler(bot_manager)
    logger.info("Scheduler iniciado com BotManager.")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not telegram_token:
        logger.warning("TELEGRAM_BOT_TOKEN não definido. Telegram desativado.")
        yield
        # SHUTDOWN abaixo ainda será executado
        stop_scheduler()
        return

    try:
        telegram_app = start_bot(telegram_token)
        await start_telegram_polling(telegram_app)

        telegram_channel = telegram_app.bot_data.get("telegram_channel")
        if telegram_channel:
            bot_manager.register_channel("telegram", telegram_channel)
            logger.info("Canal Telegram registrado no BotManager.")
        else:
            logger.error("Telegram channel ausente no bot_data.")

    except Exception:
        logger.exception("Falha no Telegram. Sistema continua com WhatsApp + Scheduler.")

    # aplicação rodando
    yield

    # ======================
    # SHUTDOWN
    # ======================
    stop_scheduler()

    if telegram_app:
        await stop_telegram_polling(telegram_app)


# ===============================
# FASTAPI APP
# ===============================
app = FastAPI(
    title="Symptom Tracker API",
    redirect_slashes=False,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    lifespan=lifespan
)

API_PREFIX = "/api"

# ===============================
# ROUTES
# ===============================
app.include_router(auth_routes.router, prefix=f"{API_PREFIX}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API_PREFIX}/anamneses")
app.include_router(daily_reports_routes.router, prefix=f"{API_PREFIX}/daily-reports")
app.include_router(insight_routes.router, prefix=f"{API_PREFIX}/insights")
app.include_router(report_routes.router, prefix=f"{API_PREFIX}/reports")
app.include_router(user_routes.router, prefix=f"{API_PREFIX}/users")
app.include_router(bot_webhook_routes.router)