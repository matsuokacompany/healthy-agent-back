from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.core.permissions import require_access_user
from app.models.models import User
from app.services.report_service import ReportService

router = APIRouter(tags=["Reports"])

PERIODOS_VALIDOS = {"diario", "semanal", "mensal"}


@router.get("/{user_id}")
def gerar_relatorio(
    user_id: int,
    periodo: str = Query("semanal"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_access_user(current_user, user_id)
    if periodo not in PERIODOS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Período inválido. Use: {', '.join(PERIODOS_VALIDOS)}",
        )

    service = ReportService(db)
    relatorio = service.gerar_relatorio(user_id, periodo)

    return {
        "user_id": user_id,
        "periodo": periodo,
        "relatorio": relatorio,
    }
