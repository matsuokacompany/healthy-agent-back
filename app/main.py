import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bot.channels.bot_manager import BotManager
from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
from app.bot.scheduler import start_scheduler, stop_scheduler, get_scheduler

from app.routes import (
    anamnese_routes,
    auth_routes,
    bot_webhook_routes,
    daily_reports_routes,
    insight_routes,
    monitoring_routes,
    patient_dashboard_routes,
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
DEFAULT_CORS_ORIGINS = "http://localhost:3000,https://app.julha.com.br"


def parse_cors_origins(cors_origins: str) -> list[str]:
    return [
        origin.strip().strip("[]")
        for origin in cors_origins.split(",")
        if origin.strip().strip("[]")
    ]


CORS_ORIGINS = parse_cors_origins(
    os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
)


# =========================================================
# LIFESPAN
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting application | env=%s", ENV)

    # =====================================================
    # BOT MANAGER (singleton por processo)
    # =====================================================
    bot_manager = BotManager()
    bot_manager.register_channel("whatsapp", WhatsAppBotChannel())

    app.state.bot_manager = bot_manager

    logger.info("BotManager inicializado")

    # =====================================================
    # SCHEDULER (proteção contra duplicação)
    # =====================================================
    existing_scheduler = get_scheduler()

    if existing_scheduler and existing_scheduler.running:
        logger.warning("Scheduler já está rodando. Evitando duplicação.")
    else:
        start_scheduler(bot_manager)
        logger.info("Scheduler iniciado")

    # =====================================================
    # APP RODANDO
    # =====================================================
    yield

    # =====================================================
    # SHUTDOWN
    # =====================================================
    logger.info("Shutting down application")

    stop_scheduler()

    logger.info("Scheduler finalizado")


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ROUTES
# =========================================================
app.include_router(auth_routes.router, prefix=f"{API_PREFIX}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API_PREFIX}/anamneses")
app.include_router(daily_reports_routes.router, prefix=f"{API_PREFIX}/daily-reports")
app.include_router(insight_routes.router, prefix=f"{API_PREFIX}/insights")
app.include_router(monitoring_routes.router, prefix=f"{API_PREFIX}/monitoring")
app.include_router(patient_dashboard_routes.router, prefix="/patient")
app.include_router(report_routes.router, prefix=f"{API_PREFIX}/reports")
app.include_router(user_routes.router, prefix=f"{API_PREFIX}/users")
app.include_router(bot_webhook_routes.router)