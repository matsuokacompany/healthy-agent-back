from fastapi import FastAPI
from app.routes import report_routes, insight_routes, user_routes, anamnese_routes, symptom_routes, daily_log_routes

app = FastAPI(title="Symptom Tracker API")

# Incluir as rotas principais
app.include_router(report_routes.router, prefix="/report", tags=["report"])
app.include_router(insight_routes.router, prefix="/insight", tags=["insight"])
app.include_router(user_routes.router, prefix="/users", tags=["users"])
app.include_router(anamnese_routes.router, prefix="/anamneses", tags=["anamneses"])
app.include_router(symptom_routes.router, prefix="/symptoms", tags=["symptoms"])
app.include_router(daily_log_routes.router, prefix="/logs", tags=["logs"])