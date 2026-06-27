from fastapi import APIRouter, Depends

from app.core.access_control import AuthenticatedContext, get_context_label
from app.core.auth import (
    require_admin_context,
    require_patient_context,
    require_professional_context,
)

admin_router = APIRouter(prefix="/admin", tags=["Admin Context"])
professional_router = APIRouter(prefix="/professional", tags=["Professional Context"])
patient_router = APIRouter(prefix="/patient", tags=["Patient Context"])


def _context_response(auth_context: AuthenticatedContext) -> dict:
    return {
        "user_id": auth_context.user.id,
        "role": auth_context.role.value,
        "active_context": auth_context.active_context.value if auth_context.active_context else None,
        "active_context_label": get_context_label(auth_context.active_context),
    }


@admin_router.get("")
def admin_context(
    auth_context: AuthenticatedContext = Depends(require_admin_context),
):
    return _context_response(auth_context)


@professional_router.get("")
def professional_context(
    auth_context: AuthenticatedContext = Depends(require_professional_context),
):
    return _context_response(auth_context)


@patient_router.get("")
def patient_context(
    auth_context: AuthenticatedContext = Depends(require_patient_context),
):
    return _context_response(auth_context)
