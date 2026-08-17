from fastapi import APIRouter, Depends
import os

from app.core.auth import get_current_professional_or_admin
from app.models.models import User
from app.services.insight_service import InsightService
from app.models.schemas import (
    InsightPreventiveResponse,
    InsightClinicalResponse,
    InsightRequest,
)

router = APIRouter(tags=["Insights"])

@router.post(
    "/preventivo",
    response_model=InsightPreventiveResponse,
)
def gerar_insight_preventivo(req: InsightRequest, _: User = Depends(get_current_professional_or_admin)):
    service = InsightService(
        api_key=os.getenv("OPENAI_API_KEY"),
        modo="preventivo",
    )
    return service.gerar_interpretacao(req.relatorio_texto)


@router.post(
    "/avaliacao-clinica",
    response_model=InsightClinicalResponse,
)
def gerar_avaliacao_clinica(req: InsightRequest, _: User = Depends(get_current_professional_or_admin)):
    service = InsightService(
        api_key=os.getenv("OPENAI_API_KEY"),
        modo="avaliacao_clinica",
    )
    return service.gerar_interpretacao(req.relatorio_texto)
