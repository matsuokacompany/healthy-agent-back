from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin, get_current_super_admin, get_current_user
from app.core.dependencies import get_db
from app.core.permissions import require_access_user
from app.models.models import User
from app.models.schemas import UserCreate, UserRead, UserRoleUpdate, UserUpdate
from app.services.user_service import UserService

router = APIRouter(tags=["Users"])


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Create a local domain user linked to a Supabase identity."""
    return UserService(db).create_user(user, current_user)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_access_user(current_user, user_id)
    return UserService(db).get_user(user_id)


@router.get("/", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    return UserService(db).list_users()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_access_user(current_user, user_id)
    UserService(db).delete_user(user_id)
    return


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_access_user(current_user, user_id)
    return UserService(db).update_user(user_id, payload)


@router.put("/{user_id}/roles", response_model=UserRead)
def update_user_roles(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    return UserService(db).update_roles(user_id, payload, current_user)
