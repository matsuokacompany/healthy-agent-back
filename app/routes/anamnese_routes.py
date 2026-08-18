from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.models import Anamnese, User
from app.models.schemas import AnamneseCreate, AnamneseRead, AnamneseUpdate
from app.core.dependencies import get_db
from app.core.auth import get_current_user
from app.core.permissions import is_admin
from app.services.anamnese_clinical_service import AnamneseClinicalService

router = APIRouter(tags=["Anamneses"])


@router.post("/", response_model=AnamneseRead, status_code=status.HTTP_201_CREATED)
def create_anamnese(
    anamnese: AnamneseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # user normal só pode criar pra ele mesmo
    if not is_admin(current_user) and anamnese.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create anamnese for another user"
        )

    # 🔥 impedir duplicado (1 anamnese por usuário)
    existing = db.query(Anamnese).filter(Anamnese.user_id == anamnese.user_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user already has an anamnese"
        )

    db_item = Anamnese(
        user_id=anamnese.user_id,
        info=AnamneseClinicalService.initial_plaintext(anamnese.info),
    )
    db.add(db_item)
    try:
        db.flush()
        AnamneseClinicalService.write(db_item, anamnese.info)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Anamnese).filter(Anamnese.user_id == anamnese.user_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This user already has an anamnese",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create anamnese due to data integrity violation",
        )

    db.refresh(db_item)
    return AnamneseClinicalService.hydrate(db_item)


@router.get("/user/{user_id}", response_model=list[AnamneseRead])
def get_user_anamneses(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # user normal só pode listar as dele
    if not is_admin(current_user) and user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )

    items = db.query(Anamnese).filter(Anamnese.user_id == user_id).all()
    return [AnamneseClinicalService.hydrate(item) for item in items]


@router.get("/me", response_model=AnamneseRead)
def get_my_anamnese(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(Anamnese).filter(Anamnese.user_id == current_user.id).first()
    if not item:
        raise HTTPException(404, "Anamnese not found")

    return AnamneseClinicalService.hydrate(item)


# ============================================================
#                     UPDATE ANAMNESE
# ============================================================
@router.put("/me", response_model=AnamneseRead)
def update_my_anamnese(
    payload: AnamneseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(Anamnese).filter(Anamnese.user_id == current_user.id).first()
    if not item:
        raise HTTPException(404, "Anamnese not found")

    data = payload.dict(exclude_unset=True)
    if "info" in data:
        AnamneseClinicalService.write(item, data["info"])

    db.commit()
    db.refresh(item)
    return AnamneseClinicalService.hydrate(item)



# ============================================================
#                     DELETE ANAMNESE
# ============================================================
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_anamnese(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Anamnese).filter(Anamnese.id == id)
    if not is_admin(current_user):
        query = query.filter(Anamnese.user_id == current_user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Anamnese not found")

    db.delete(item)
    db.commit()
    return
