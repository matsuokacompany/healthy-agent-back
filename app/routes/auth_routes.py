from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.access_control import (
    AccessContext,
    AuthenticatedContext,
    UserRole,
    assert_super_admin,
    get_context_label,
    get_context_redirect,
    get_default_context,
    get_login_redirect,
    get_user_role,
)
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    get_current_auth_context,
    get_current_user,
    verify_password,
)
from app.core.dependencies import get_db
from app.models.models import RefreshToken, User
from app.models.schemas import (
    AuthLoginResponse,
    AuthUserPayload,
    ChooseContextRequest,
    ChooseContextResponse,
    RefreshTokenRequest,
)

router = APIRouter(tags=["Auth"])


def _build_auth_user_payload(
    user: User,
    role: UserRole,
    active_context: AccessContext | None,
) -> AuthUserPayload:
    return AuthUserPayload(
        id=user.id,
        name=user.name,
        email=user.email,
        role=role.value,
        active_context=active_context.value if active_context else None,
        active_context_label=get_context_label(active_context),
    )


# =========================
# LOGIN
# =========================

@router.post("/login", response_model=AuthLoginResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(email=form.username).first()

    if not user or not user.hashed_password:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    role = get_user_role(user)
    active_context = get_default_context(role)
    access_token = create_access_token(user.id, active_context=active_context)
    refresh_token, expires_at = create_refresh_token()

    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
        )
    )
    db.commit()

    return AuthLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        redirect_to=get_login_redirect(role),
        user=_build_auth_user_payload(user, role, active_context),
    )


@router.get("/me", response_model=AuthUserPayload)
def get_me(
    auth_context: AuthenticatedContext = Depends(get_current_auth_context),
):
    return _build_auth_user_payload(
        auth_context.user,
        auth_context.role,
        auth_context.active_context,
    )


@router.get("/contexts")
def list_available_contexts(
    current_user: User = Depends(get_current_user),
):
    assert_super_admin(current_user)

    return {
        "message": "Escolha como deseja acessar a plataforma.",
        "contexts": [
            {
                "context": AccessContext.ADMIN.value,
                "label": get_context_label(AccessContext.ADMIN),
                "redirect_to": get_context_redirect(AccessContext.ADMIN),
            },
            {
                "context": AccessContext.PROFESSIONAL.value,
                "label": get_context_label(AccessContext.PROFESSIONAL),
                "redirect_to": get_context_redirect(AccessContext.PROFESSIONAL),
            },
            {
                "context": AccessContext.PATIENT.value,
                "label": get_context_label(AccessContext.PATIENT),
                "redirect_to": get_context_redirect(AccessContext.PATIENT),
            },
        ],
    }


@router.post("/context", response_model=ChooseContextResponse)
def choose_context(
    data: ChooseContextRequest,
    current_user: User = Depends(get_current_user),
):
    assert_super_admin(current_user)

    active_context = AccessContext(data.context)
    access_token = create_access_token(current_user.id, active_context=active_context)
    role = UserRole.SUPER_ADMIN

    return ChooseContextResponse(
        access_token=access_token,
        token_type="bearer",
        redirect_to=get_context_redirect(active_context),
        user=_build_auth_user_payload(current_user, role, active_context),
    )


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

    db_token.revoked = True

    user = db.query(User).filter(User.id == db_token.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    role = get_user_role(user)
    active_context = get_default_context(role)
    new_access_token = create_access_token(db_token.user_id, active_context=active_context)
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
        "redirect_to": get_login_redirect(role),
        "user": _build_auth_user_payload(user, role, active_context),
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
