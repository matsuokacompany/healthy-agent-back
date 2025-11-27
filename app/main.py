from fastapi import FastAPI
from app.routes.report_routes import router as report_router
from app.routes.insight_routes import router as insight_router

app = FastAPI(title="Healthy Agent API")

# Registrar rotas
app.include_router(report_router, prefix="/reports", tags=["Relatórios"])
app.include_router(insight_router, prefix="/insights", tags=["Insights"])
