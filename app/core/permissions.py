from fastapi import HTTPException, status
from app.models.models import User

SUPER_ADMIN_EMAIL = "matsuokacompany@gmail.com"
SUPER_ADMIN_ID = 1

def is_super_admin(user: User) -> bool:
    return user.id == SUPER_ADMIN_ID and user.email == SUPER_ADMIN_EMAIL


def can_access_user(current_user: User, target_user_id: int) -> bool:
    return current_user.is_admin or current_user.id == target_user_id


def require_access_user(current_user: User, target_user_id: int):
    if not can_access_user(current_user, target_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
