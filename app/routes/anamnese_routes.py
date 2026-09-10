from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.models import Anamnese, MonitoringPlan, MonitoringPlanOriginEnum, User
from app.models.schemas import AnamneseBase, AnamneseCreate, AnamneseRead, AnamneseUpdate
from app.core.dependencies import get_db
from app.core.auth import get_current_user
from app.core.permissions import is_admin
from app.services.anamnese_clinical_service import AnamneseClinicalService
from app.services.red_flag_symptoms import ANAMNESE_RISK_FACTOR_FIELDS

router = APIRouter(tags=["Anamneses"])


def _has_professional_monitoring(db: Session, patient_id: int) -> bool:
    return (
        db.query(MonitoringPlan)
        .filter(
            MonitoringPlan.patient_id == patient_id,
            MonitoringPlan.origin == MonitoringPlanOriginEnum.PROFESSIONAL.value,
            MonitoringPlan.active.is_(True),
        )
        .first()
        is not None
    )


def _require_clinical_write_access(current_user: User, target_user_id: int, db: Session) -> None:
    # Anamnese is normally professional-authored clinical content, and this
    # generic, patient-id-unscoped route must not be usable to write someone
    # else's: a professional writing here would bypass AccessPolicy's check
    # that they are actually linked to that specific patient (they write
    # anamnese only through app/routes/professional_routes.py, which enforces
    # that link). Admins are trusted with the unscoped path for support needs.
    #
    # A patient with no active professional-monitored plan has nobody to ask
    # for one, so they're allowed to write their own -- but only their own,
    # and only while that stays true; the moment a professional plan links
    # them, this reverts to read-only so it can't be used to override the
    # professional's own record.
    if is_admin(current_user):
        return
    if current_user.id == target_user_id and not _has_professional_monitoring(db, target_user_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only admins, or a self-service patient writing their own anamnese, can write through this endpoint",
    )


def _create_anamnese(db: Session, user_id: int, info: str, risk_factors: dict | None = None) -> Anamnese:
    # 🔥 impedir duplicado (1 anamnese por usuário)
    existing = db.query(Anamnese).filter(Anamnese.user_id == user_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user already has an anamnese"
        )

    db_item = Anamnese(
        user_id=user_id,
        info=AnamneseClinicalService.initial_plaintext(info),
    )
    db.add(db_item)
    try:
        db.flush()
        AnamneseClinicalService.write(db_item, info)
        if risk_factors:
            AnamneseClinicalService.write_risk_factors(db_item, risk_factors)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Anamnese).filter(Anamnese.user_id == user_id).first()
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


@router.post("/", response_model=AnamneseRead, status_code=status.HTTP_201_CREATED)
def create_anamnese(
    anamnese: AnamneseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_clinical_write_access(current_user, anamnese.user_id, db)
    risk_factors = anamnese.dict(exclude_unset=True, include=set(ANAMNESE_RISK_FACTOR_FIELDS))
    return _create_anamnese(db, anamnese.user_id, anamnese.info, risk_factors)


@router.post("/me", response_model=AnamneseRead, status_code=status.HTTP_201_CREATED)
def create_my_anamnese(
    payload: AnamneseBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-scoped create, for a self-service patient writing their own
    anamnese for the first time -- doesn't require the client to know its
    own internal user id, unlike the generic POST /."""
    _require_clinical_write_access(current_user, current_user.id, db)
    risk_factors = payload.dict(exclude_unset=True, include=set(ANAMNESE_RISK_FACTOR_FIELDS))
    return _create_anamnese(db, current_user.id, payload.info, risk_factors)


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
    _require_clinical_write_access(current_user, current_user.id, db)
    item = db.query(Anamnese).filter(Anamnese.user_id == current_user.id).first()
    if not item:
        raise HTTPException(404, "Anamnese not found")

    data = payload.dict(exclude_unset=True)
    if "info" in data:
        AnamneseClinicalService.write(item, data["info"])
    AnamneseClinicalService.write_risk_factors(item, data)

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
