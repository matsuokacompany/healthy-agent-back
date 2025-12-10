from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.models import DailyLog
from app.models.schemas import DailyLogCreate, DailyLogRead
from app.core.dependencies import get_db

router = APIRouter(prefix="/logs", tags=["Daily Logs"])

@router.post("/", response_model=DailyLogRead)
def create_log(data: DailyLogCreate, db: Session = Depends(get_db)):
    obj = DailyLog(**data.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@router.get("/user/{user_id}", response_model=list[DailyLogRead])
def get_user_logs(user_id: int, db: Session = Depends(get_db)):
    return db.query(DailyLog).filter(DailyLog.user_id == user_id).all()

@router.get("/{id}", response_model=DailyLogRead)
def get_log(id: int, db: Session = Depends(get_db)):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(404, "Log not found")
    return log
