from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import SupplementCreate, SupplementRead
from app.services.supplement_service import SupplementService

router = APIRouter(tags=["Supplements"])


@router.get("/me", response_model=list[SupplementRead])
def list_my_supplements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SupplementService(db).list_for_patient(current_user.id)


@router.post("/", response_model=SupplementRead, status_code=status.HTTP_201_CREATED)
def create_my_supplement(
    payload: SupplementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SupplementService(db).create(current_user, payload.name)


@router.delete("/{supplement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_supplement(
    supplement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = SupplementService(db).delete(current_user, supplement_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplement not found")
    return None
