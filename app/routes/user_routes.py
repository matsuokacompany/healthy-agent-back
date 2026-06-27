from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets

from app.models.schemas import UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService
from app.core.dependencies import get_db
from app.core.auth import get_current_user, get_current_admin, get_current_user_optional
from app.models.models import User, TelegramLinkCode
from app.core.access_control import UserRole, get_user_role

router = APIRouter(tags=["Users"])

# ============================================================
#                     CREATE USER (ADMIN)
# ============================================================

@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    - Qualquer um pode criar usuário normal
    - Só super admin pode criar admin
    """

    # se tentar criar usuário administrativo/profissional/super admin...
    creates_privileged_user = user.is_admin or user.role in {UserRole.PROFESSIONAL.value, UserRole.SUPER_ADMIN.value}
    if creates_privileged_user:
        # precisa estar logado
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to create admin user"
            )

        # e precisa ser super admin
        if get_user_role(current_user) != UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admin can create privileged users"
            )

    service = UserService(db)
    return service.create_user(user)

# ============================================================
#                  GET USER (SELF OR ADMIN)
# ============================================================

@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.permissions import require_access_user
    require_access_user(current_user, user_id)

    return UserService(db).get_user(user_id)


# ============================================================
#                  LIST USERS (ADMIN ONLY)
# ============================================================

@router.get("/", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return UserService(db).list_users()


# ============================================================
#                  DELETE USER (ADMIN ONLY)
# ============================================================
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.permissions import require_access_user
    require_access_user(current_user, user_id)

    UserService(db).delete_user(user_id)
    return

# ============================================================
#                  UPDATE USER (SELF OR ADMIN)
# ============================================================
@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.permissions import require_access_user
    require_access_user(current_user, user_id)

    return UserService(db).update_user(user_id, payload, current_user)

# ============================================================
#                  GENERATE TELEGRAM LINK CODE
# ============================================================

@router.post("/me/generate-telegram-code")
def generate_telegram_code(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    code = secrets.token_hex(3).upper()

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    link = TelegramLinkCode(
        user_id=current_user.id,
        code=code,
        expires_at=expires_at,
    )

    db.add(link)
    db.commit()

    return {
        "telegram_code": code,
        "expires_at": expires_at
    }