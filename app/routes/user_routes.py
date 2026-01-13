from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.schemas import UserCreate, UserRead
from app.services.user_service import UserService
from app.core.dependencies import get_db
from app.core.auth import get_current_user, get_current_admin
from app.models.models import User

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


# ============================================================
#                     CREATE USER (ADMIN)
# ============================================================

@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED
)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin)  # apenas admin
):
    service = UserService(db)
    return service.create_user(user)


# ============================================================
#                  GET USER (SELF OR ADMIN)
# ============================================================

@router.get(
    "/{user_id}",
    response_model=UserRead
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Se não for admin, só pode acessar o próprio usuário
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user"
        )

    service = UserService(db)
    return service.get_user(user_id)


# ============================================================
#                  LIST USERS (ADMIN ONLY)
# ============================================================

@router.get(
    "/",
    response_model=list[UserRead]
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin)  # apenas admin
):
    service = UserService(db)
    return service.list_users()
