import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bot.channels.bot_manager import BotManager
from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
from app.bot.scheduler import start_scheduler, stop_scheduler

from app.bot.telegram_bot import (
    start_bot,
    start_telegram_polling,
    stop_telegram_polling,
)

from app.routes import (
    anamnese_routes,
    auth_routes,
    bot_webhook_routes,
    daily_reports_routes,
    insight_routes,
    report_routes,
    user_routes,
)

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

ENV = os.getenv("ENV", "dev").lower()
DEBUG = ENV == "dev"

telegram_app = None


# =========================================================
# LIFESPAN
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    # -------------------------
    # BOT MANAGER (CORE)
    # -------------------------
    bot_manager = BotManager()

    bot_manager.register_channel("whatsapp", WhatsAppBotChannel())
    app.state.bot_manager = bot_manager

    logger.info("BotManager inicializado com WhatsApp")

    # -------------------------
    # SCHEDULER (INDEPENDENTE)
    # -------------------------
    start_scheduler(bot_manager)
    logger.info("Scheduler iniciado com BotManager")

    # -------------------------
    # TELEGRAM (OPCIONAL)
    # -------------------------
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if telegram_token:
        try:
            telegram_app = start_bot(telegram_token)
            await start_telegram_polling(telegram_app)

            telegram_channel = telegram_app.bot_data.get("telegram_channel")

            if telegram_channel:
                bot_manager.register_channel("telegram", telegram_channel)
                logger.info("Telegram habilitado e registrado no BotManager")
            else:
                logger.warning("Telegram iniciado, mas canal não encontrado")

        except Exception:
            logger.exception("Falha ao iniciar Telegram — sistema segue sem ele")
    else:
        logger.warning("Telegram desativado (sem TELEGRAM_BOT_TOKEN)")

    # -------------------------
    # APP RODANDO
    # -------------------------
    yield

    # -------------------------
    # SHUTDOWN LIMPO
    # -------------------------
    stop_scheduler()

    if telegram_app:
        await stop_telegram_polling(telegram_app)
        logger.info("Telegram finalizado")


# =========================================================
# FASTAPI APP
# =========================================================
app = FastAPI(
    title="Symptom Tracker API",
    redirect_slashes=False,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    lifespan=lifespan,
)

API_PREFIX = "/api"


# =========================================================
# ROUTES
# =========================================================
app.include_router(auth_routes.router, prefix=f"{API_PREFIX}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API_PREFIX}/anamneses")
app.include_router(daily_reports_routes.router, prefix=f"{API_PREFIX}/daily-reports")
app.include_router(insight_routes.router, prefix=f"{API_PREFIX}/insights")
app.include_router(report_routes.router, prefix=f"{API_PREFIX}/reports")
app.include_router(user_routes.router, prefix=f"{API_PREFIX}/users")
app.include_router(bot_webhook_routes.router)