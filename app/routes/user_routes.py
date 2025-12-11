from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.schemas import UserCreate, UserRead
from app.services.user_service import UserService
from app.core.dependencies import get_db

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", response_model=UserRead)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    service = UserService(db)
    return service.create_user(user)

@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)):
    service = UserService(db)
    return service.get_user(user_id)

@router.get("/", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    service = UserService(db)
    return service.list_users()
