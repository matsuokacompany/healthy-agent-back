from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, status

from app.models.models import User

SUPER_ADMIN_EMAIL = "matsuokacompany@gmail.com"
SUPER_ADMIN_ID = 1


class UserRole(str, Enum):
    PATIENT = "patient"
    PROFESSIONAL = "professional"
    SUPER_ADMIN = "super_admin"


class AccessContext(str, Enum):
    ADMIN = "admin"
    PROFESSIONAL = "professional"
    PATIENT = "patient"


ROLE_DEFAULT_CONTEXT: dict[UserRole, AccessContext | None] = {
    UserRole.PATIENT: AccessContext.PATIENT,
    UserRole.PROFESSIONAL: AccessContext.PROFESSIONAL,
    UserRole.SUPER_ADMIN: None,
}

ROLE_REDIRECTS: dict[UserRole, str] = {
    UserRole.PATIENT: "/patient",
    UserRole.PROFESSIONAL: "/professional",
    UserRole.SUPER_ADMIN: "/choose-context",
}

CONTEXT_REDIRECTS: dict[AccessContext, str] = {
    AccessContext.ADMIN: "/admin",
    AccessContext.PROFESSIONAL: "/professional",
    AccessContext.PATIENT: "/patient",
}

CONTEXT_LABELS: dict[AccessContext, str] = {
    AccessContext.ADMIN: "Administração",
    AccessContext.PROFESSIONAL: "Profissional",
    AccessContext.PATIENT: "Paciente",
}


@dataclass(frozen=True)
class AuthenticatedContext:
    user: User
    role: UserRole
    active_context: AccessContext | None


def is_hardcoded_super_admin(user: User) -> bool:
    return user.id == SUPER_ADMIN_ID and user.email == SUPER_ADMIN_EMAIL


def get_user_role(user: User) -> UserRole:
    raw_role = getattr(user, "role", None)
    if raw_role:
        try:
            return UserRole(raw_role)
        except ValueError:
            pass

    if is_hardcoded_super_admin(user):
        return UserRole.SUPER_ADMIN

    if user.is_admin:
        return UserRole.PROFESSIONAL

    return UserRole.PATIENT


def get_default_context(role: UserRole) -> AccessContext | None:
    return ROLE_DEFAULT_CONTEXT[role]


def get_login_redirect(role: UserRole) -> str:
    return ROLE_REDIRECTS[role]


def get_context_redirect(context: AccessContext) -> str:
    return CONTEXT_REDIRECTS[context]


def get_context_label(context: AccessContext | None) -> str | None:
    if context is None:
        return None
    return CONTEXT_LABELS[context]


def assert_super_admin(user: User) -> None:
    if get_user_role(user) != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )


def assert_context_allowed(role: UserRole, context: AccessContext | None) -> None:
    if role == UserRole.SUPER_ADMIN:
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Access context required. Choose a context first.",
            )
        return

    expected_context = get_default_context(role)
    if context != expected_context:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access context is not allowed for this user role",
        )


def assert_can_access_context(auth_context: AuthenticatedContext, required_context: AccessContext) -> None:
    assert_context_allowed(auth_context.role, auth_context.active_context)

    if auth_context.active_context != required_context:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{required_context.value} context required",
        )
