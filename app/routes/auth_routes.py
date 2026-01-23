from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.auth import verify_password, create_access_token, get_current_user
from app.models.models import User
from app.models.schemas import UserCreate, UserRead
from app.services.user_service import UserService
from app.core.permissions import is_super_admin

router = APIRouter(tags=["Auth"])


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter_by(email=form.username).first()

    if not user or not user.hashed_password:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(user.id, expires_delta=60)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/admin", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 🔐 precisa estar logado (get_current_user)
    # 👑 precisa ser super admin
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create admin users"
        )

    user.is_admin = True
    return UserService(db).create_user(user, current_user)
