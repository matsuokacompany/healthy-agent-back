from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import Symptom, User
from app.models.schemas import SymptomCreate, SymptomRead
from app.core.dependencies import get_db
from app.core.auth import get_current_user

router = APIRouter(tags=["Symptoms"])

@router.post("/", response_model=SymptomRead)
def create_symptom(
    data: SymptomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = Symptom(
        user_id=current_user.id,
        **data.model_dump(exclude={"user_id"})
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/", response_model=list[SymptomRead])
def get_my_symptoms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Symptom)
        .filter(Symptom.user_id == current_user.id)
        .all()
    )


@router.get("/{id}", response_model=SymptomRead)
def get_symptom(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(Symptom)
        .filter(
            Symptom.id == id,
            Symptom.user_id == current_user.id,
        )
        .first()
    )

    if not item:
        raise HTTPException(404, "Symptom not found")

    return item
