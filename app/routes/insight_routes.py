from fastapi import APIRouter
from pydantic import BaseModel
from app.services.insight_service import InsightService
import os

router = APIRouter(tags=["Insights"])

class InsightRequest(BaseModel):
    relatorio_texto: str

@router.post("/")
def gerar_insight(req: InsightRequest):
    api_key = os.getenv("OPENAI_API_KEY", "")
    service = InsightService(api_key)
    return {"insight": service.gerar_interpretacao(req.relatorio_texto)}
