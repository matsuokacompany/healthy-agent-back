from fastapi import HTTPException, status

from app.core.access_control import UserRole, get_user_role
from app.models.models import User


def is_super_admin(user: User) -> bool:
    return get_user_role(user) == UserRole.SUPER_ADMIN


def can_access_user(current_user: User, target_user_id: int) -> bool:
    role = get_user_role(current_user)
    return role in {UserRole.SUPER_ADMIN, UserRole.PROFESSIONAL} or current_user.id == target_user_id


def require_access_user(current_user: User, target_user_id: int):
    if not can_access_user(current_user, target_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
