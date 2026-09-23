from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import AllergyCreate, AllergyRead, AllergyUpdate
from app.services.allergy_service import AllergyService

router = APIRouter(tags=["Allergies"])


@router.get("/me", response_model=list[AllergyRead])
def list_my_allergies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AllergyService(db).list_for_patient(current_user.id)


@router.post("/", response_model=AllergyRead, status_code=status.HTTP_201_CREATED)
def create_my_allergy(
    payload: AllergyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AllergyService(db).create(current_user, payload.allergen, severity=payload.severity)


@router.patch("/{allergy_id}", response_model=AllergyRead)
def update_my_allergy(
    allergy_id: int,
    payload: AllergyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = AllergyService(db).update(current_user, allergy_id, **payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allergy not found")
    return updated


@router.delete("/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_allergy(
    allergy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = AllergyService(db).delete(current_user, allergy_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allergy not found")
    return None
