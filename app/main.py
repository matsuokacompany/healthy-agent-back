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

app = FastAPI(
    title="Symptom Tracker API",
    docs_url=None,
    redoc_url=None
)

API = "/api"
app.include_router(auth_routes.router, prefix="/api")
app.include_router(anamnese_routes.router, prefix=f"{API}/anamneses")
app.include_router(daily_log_routes.router, prefix=f"{API}/logs")
app.include_router(insight_routes.router, prefix=f"{API}/insights")
app.include_router(report_routes.router, prefix=f"{API}/reports")
app.include_router(symptom_routes.router, prefix=f"{API}/symptoms")
app.include_router(user_routes.router, prefix=f"{API}/users")
