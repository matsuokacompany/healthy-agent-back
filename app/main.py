import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.bot.channels.bot_manager import BotManager
from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
from app.bot.scheduler import start_scheduler, stop_scheduler, get_scheduler
from app.core.config import settings
from app.core.rate_limit import limiter

from app.routes import (
    admin_routes,
    anamnese_routes,
    auth_routes,
    bot_webhook_routes,
    clinical_attachment_routes,
    daily_reports_routes,
    insight_routes,
    legal_routes,
    monitoring_routes,
    notification_routes,
    patient_dashboard_routes,
    patient_link_routes,
    payment_routes,
    professional_routes,
    report_routes,
    self_monitoring_routes,
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def csrf_and_origin_protection(request: Request, call_next):
    unsafe_method = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    if unsafe_method and request.url.path.startswith(API_PREFIX):
        origin = request.headers.get("origin")
        if origin and origin not in CORS_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "Invalid origin"})
        csrf_exempt = {
            f"{API_PREFIX}/auth/login",
            f"{API_PREFIX}/auth/signup",
            f"{API_PREFIX}/auth/signup-professional",
            f"{API_PREFIX}/auth/forgot-password",
            f"{API_PREFIX}/auth/callback",
        }
        access_cookie = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        bearer_auth = request.headers.get("Authorization", "").lower().startswith("bearer ")
        uses_cookie_auth = bool(access_cookie) or not bearer_auth
        if request.url.path not in csrf_exempt and uses_cookie_auth:
            csrf_cookie = request.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
            csrf_header = request.headers.get(settings.AUTH_CSRF_HEADER_NAME)
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                return JSONResponse(status_code=403, content={"detail": "Invalid CSRF token"})
    response = await call_next(request)
    if request.url.path.startswith(f"{API_PREFIX}/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", settings.AUTH_CSRF_HEADER_NAME],
    expose_headers=[settings.AUTH_CSRF_HEADER_NAME],
)


# =========================================================
# ROUTES
# =========================================================
app.include_router(admin_routes.router, prefix=f"{API_PREFIX}/admin")
app.include_router(auth_routes.router, prefix=f"{API_PREFIX}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API_PREFIX}/anamneses")
app.include_router(daily_reports_routes.router, prefix=f"{API_PREFIX}/daily-reports")
app.include_router(insight_routes.router, prefix=f"{API_PREFIX}/insights")
app.include_router(legal_routes.router, prefix=f"{API_PREFIX}/legal")
app.include_router(monitoring_routes.router, prefix=f"{API_PREFIX}/monitoring")
app.include_router(notification_routes.router, prefix=f"{API_PREFIX}/notifications")
app.include_router(patient_dashboard_routes.router, prefix="/patient")
app.include_router(patient_link_routes.router, prefix=f"{API_PREFIX}/patient-links")
app.include_router(professional_routes.router, prefix=f"{API_PREFIX}/professional")
app.include_router(report_routes.router, prefix=f"{API_PREFIX}/reports")
app.include_router(self_monitoring_routes.router, prefix=f"{API_PREFIX}/self-monitoring")
app.include_router(user_routes.router, prefix=f"{API_PREFIX}/users")
app.include_router(bot_webhook_routes.router)
app.include_router(clinical_attachment_routes.router, prefix=f"{API_PREFIX}/clinical-attachments")
app.include_router(payment_routes.router, prefix=f"{API_PREFIX}/billing")
app.include_router(payment_routes.webhook_router)
