from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.models import User
from app.models.schemas import UserRead

router = APIRouter(tags=["Auth"])


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    """Return the local domain user resolved from a valid Supabase Auth JWT."""
    return current_user
