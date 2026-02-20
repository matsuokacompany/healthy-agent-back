import os
from fastapi import FastAPI

from app.routes import (
    auth_routes,
    anamnese_routes,
    daily_log_routes,
    insight_routes,
    report_routes,
    symptom_routes,
    user_routes
)

from app.bot.telegram_bot import start_bot
from app.bot.scheduler import schedule_daily_messages

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout  # importante para aparecer no docker logs
)

ENV = os.getenv("ENV", "dev").lower()
DEBUG = ENV == "dev"

app = FastAPI(
    title="Symptom Tracker API",
    redirect_slashes=False,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None
)

API = "/api"

# Rotas da API
app.include_router(auth_routes.router, prefix=f"{API}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API}/anamneses")
app.include_router(daily_log_routes.router, prefix=f"{API}/logs")
app.include_router(insight_routes.router, prefix=f"{API}/insights")
app.include_router(report_routes.router, prefix=f"{API}/reports")
app.include_router(symptom_routes.router, prefix=f"{API}/symptoms")
app.include_router(user_routes.router, prefix=f"{API}/users")


@app.on_event("startup")
async def startup_event():
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_app = start_bot(telegram_token)

    # Agenda a mensagem diária das 22h
    schedule_daily_messages(telegram_app)

    # Inicializa o bot
    await telegram_app.initialize()
    await telegram_app.start()

    # Inicia polling (ver logs de getUpdates, mas não envia mensagens extras)
    await telegram_app.updater.start_polling()

    logging.info("Bot e Scheduler inicializados ✅")