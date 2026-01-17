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

# from app.bot.scheduler import start_scheduler

ENV = os.getenv("ENV", "dev").lower()
DEBUG = ENV == "dev"

app = FastAPI(
    title="Symptom Tracker API",
    redirect_slashes=False,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None
)

# @app.on_event("startup")
# def startup_event():
    # start_scheduler()


API = "/api"
app.include_router(auth_routes.router, prefix=f"{API}/auth")
app.include_router(anamnese_routes.router, prefix=f"{API}/anamneses")
app.include_router(daily_log_routes.router, prefix=f"{API}/logs")
app.include_router(insight_routes.router, prefix=f"{API}/insights")
app.include_router(report_routes.router, prefix=f"{API}/reports")
app.include_router(symptom_routes.router, prefix=f"{API}/symptoms")
app.include_router(user_routes.router, prefix=f"{API}/users")
