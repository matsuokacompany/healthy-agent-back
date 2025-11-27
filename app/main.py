from fastapi import FastAPI
from app.routes import report_routes, insight_routes

app = FastAPI(title="Symptom Tracker API")

# Incluir as rotas principais
app.include_router(report_routes.router, prefix="/report", tags=["report"])
app.include_router(insight_routes.router, prefix="/insight", tags=["insight"])
