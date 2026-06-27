import logging
import os
import sys

from fastapi import FastAPI

from app.bot.scheduler import start_scheduler, stop_scheduler
from app.bot.telegram_bot import start_bot
from app.routes import (
    anamnese_routes,
    auth_routes,
    context_routes,
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
app.include_router(context_routes.admin_router, prefix=API_PREFIX)
app.include_router(context_routes.professional_router, prefix=API_PREFIX)
app.include_router(context_routes.patient_router, prefix=API_PREFIX)
app.include_router(anamnese_routes.router, prefix=f"{API_PREFIX}/anamneses")
app.include_router(daily_reports_routes.router, prefix=f"{API_PREFIX}/daily-reports")
app.include_router(insight_routes.router, prefix=f"{API_PREFIX}/insights")
app.include_router(report_routes.router, prefix=f"{API_PREFIX}/reports")
app.include_router(user_routes.router, prefix=f"{API_PREFIX}/users")

# ===============================
# Bot Telegram
# ===============================
telegram_app = None


@app.on_event("startup")
async def startup_event():
    global telegram_app
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not telegram_token:
        logging.warning("TELEGRAM_BOT_TOKEN não definido. Bot não será iniciado.")
        return

    telegram_app = start_bot(telegram_token)

    await telegram_app.initialize()
    await telegram_app.start()

    start_scheduler(telegram_app)
    logging.info("Bot Telegram inicializado ✅")


@app.on_event("shutdown")
async def shutdown_event():
    global telegram_app

    stop_scheduler()

    if telegram_app:
        updater = getattr(telegram_app, "updater", None)
        if updater and updater.running:
            await updater.stop()

        await telegram_app.stop()
        await telegram_app.shutdown()
        logging.info("Bot Telegram finalizado ✅")
