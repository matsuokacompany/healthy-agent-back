from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import DailyLog, User
from app.models.schemas import DailyLogCreate, DailyLogRead
from app.core.dependencies import get_db
from app.core.auth import get_current_user

router = APIRouter(tags=["Daily Logs"])

@router.post("/", response_model=DailyLogRead)
def create_log(
    data: DailyLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = DailyLog(
        user_id=current_user.id,
        **data.model_dump(exclude={"user_id"})
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/", response_model=list[DailyLogRead])
def get_my_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(DailyLog)
        .filter(DailyLog.user_id == current_user.id)
        .all()
    )


@router.get("/{id}", response_model=DailyLogRead)
def get_log(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = (
        db.query(DailyLog)
        .filter(
            DailyLog.id == id,
            DailyLog.user_id == current_user.id,
        )
        .first()
    )

    if not log:
        raise HTTPException(404, "Log not found")

    return log
