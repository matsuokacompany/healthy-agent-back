from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.models import Anamnese
from app.models.schemas import AnamneseCreate, AnamneseRead
from app.routes.dependencies import get_db

router = APIRouter(prefix="/anamneses", tags=["Anamnese"])

@router.post("/", response_model=AnamneseRead)
def create_anamnese(anamnese: AnamneseCreate, db: Session = Depends(get_db)):
    db_item = Anamnese(**anamnese.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.get("/user/{user_id}", response_model=list[AnamneseRead])
def get_user_anamneses(user_id: int, db: Session = Depends(get_db)):
    return db.query(Anamnese).filter(Anamnese.user_id == user_id).all()

@router.get("/{id}", response_model=AnamneseRead)
def get_anamnese(id: int, db: Session = Depends(get_db)):
    item = db.query(Anamnese).filter(Anamnese.id == id).first()
    if not item:
        raise HTTPException(404, "Anamnese not found")
    return item
