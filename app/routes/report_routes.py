from fastapi import APIRouter, Depends
from app.services.report_service import ReportService
from app.db.session import SessionLocal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{user_id}")
def gerar_relatorio(user_id: int, periodo: str = "semanal", db=Depends(get_db)):
    service = ReportService(db)
    return {"relatorio": service.gerar_relatorio(user_id, periodo)}
