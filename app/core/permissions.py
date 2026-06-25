from fastapi import HTTPException, status

from app.models.models import RoleNameEnum, User

ADMIN_ROLES = {RoleNameEnum.ADMIN.value, RoleNameEnum.SUPER_ADMIN.value}


def user_role_names(user: User) -> set[str]:
    return {role.name for role in getattr(user, "role_records", [])}


def has_role(user: User, role: RoleNameEnum | str) -> bool:
    role_name = role.value if isinstance(role, RoleNameEnum) else role
    return role_name in user_role_names(user)


def has_any_role(user: User, roles: set[RoleNameEnum | str]) -> bool:
    role_names = {role.value if isinstance(role, RoleNameEnum) else role for role in roles}
    return bool(user_role_names(user) & role_names)


def is_super_admin(user: User) -> bool:
    return has_role(user, RoleNameEnum.SUPER_ADMIN)


def is_admin(user: User) -> bool:
    return has_any_role(user, ADMIN_ROLES)


def can_access_user(current_user: User, target_user_id: int) -> bool:
    return is_admin(current_user) or current_user.id == target_user_id


def require_access_user(current_user: User, target_user_id: int):
    if not can_access_user(current_user, target_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )


def require_role(user: User, role: RoleNameEnum | str):
    if not has_role(user, role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )


def require_any_role(user: User, roles: set[RoleNameEnum | str]):
    if not has_any_role(user, roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )
