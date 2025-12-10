from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.models import Symptom
from app.models.schemas import SymptomCreate, SymptomRead
from app.routes.dependencies import get_db

router = APIRouter(prefix="/symptoms", tags=["Symptoms"])

@router.post("/", response_model=SymptomRead)
def create_symptom(data: SymptomCreate, db: Session = Depends(get_db)):
    obj = Symptom(**data.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@router.get("/user/{user_id}", response_model=list[SymptomRead])
def get_user_symptoms(user_id: int, db: Session = Depends(get_db)):
    return db.query(Symptom).filter(Symptom.user_id == user_id).all()

@router.get("/{id}", response_model=SymptomRead)
def get_symptom(id: int, db: Session = Depends(get_db)):
    item = db.query(Symptom).filter(Symptom.id == id).first()
    if not item:
        raise HTTPException(404, "Symptom not found")
    return item
