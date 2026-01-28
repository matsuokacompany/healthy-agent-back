from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from app.core.dependencies import get_db
from app.core.auth import (
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.models.models import User, RefreshToken
from app.models.schemas import RefreshTokenRequest

router = APIRouter(tags=["Auth"])

# =========================
# LOGIN
# =========================

@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(email=form.username).first()

    if not user or not user.hashed_password:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    access_token = create_access_token(user.id)
    refresh_token, expires_at = create_refresh_token()

    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
        )
    )
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

# =========================
# REFRESH
# =========================

@router.post("/refresh")
def refresh_access_token(
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token == data.refresh_token,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    if not db_token:
        raise HTTPException(401, "Invalid refresh token")

    # 🔐 revoga o antigo
    db_token.revoked = True

    # 🔁 cria novos tokens
    new_access_token = create_access_token(db_token.user_id)
    new_refresh_token, expires_at = create_refresh_token()

    db.add(
        RefreshToken(
            user_id=db_token.user_id,
            token=new_refresh_token,
            expires_at=expires_at,
        )
    )

    db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }

# =========================
# LOGOUT
# =========================

@router.post("/logout")
def logout(
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == data.refresh_token)
        .first()
    )

    if token:
        token.revoked = True
        db.commit()

    return {"ok": True}
