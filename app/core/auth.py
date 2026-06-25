from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib.request import urlopen
import json
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.permissions import is_admin, is_super_admin
from app.models.models import Role, RoleNameEnum, User, UserRole

ALGORITHMS = ["HS256", "RS256", "ES256"]

bearer_scheme = HTTPBearer()
bearer_scheme_optional = HTTPBearer(auto_error=False)


def _supabase_project_url() -> str | None:
    if not settings.SUPABASE_PROJECT_URL:
        return None
    return settings.SUPABASE_PROJECT_URL.rstrip("/")


def _supabase_jwt_issuer() -> str | None:
    if settings.SUPABASE_JWT_ISSUER:
        return settings.SUPABASE_JWT_ISSUER.rstrip("/")
    project_url = _supabase_project_url()
    if project_url:
        return f"{project_url}/auth/v1"
    return None


def _supabase_jwks_url() -> str | None:
    if settings.SUPABASE_JWKS_URL:
        return settings.SUPABASE_JWKS_URL
    project_url = _supabase_project_url()
    if project_url:
        return project_url + "/auth/v1/.well-known/jwks.json"
    return None


@lru_cache(maxsize=1)
def _load_jwks() -> dict[str, Any]:
    jwks_url = _supabase_jwks_url()
    if not jwks_url:
        raise RuntimeError("SUPABASE_JWKS_URL or SUPABASE_PROJECT_URL must be configured for asymmetric JWT validation")
    with urlopen(jwks_url, timeout=5) as response:  # nosec B310 - URL comes from trusted deployment config.
        return json.loads(response.read().decode("utf-8"))


def _find_jwk(kid: str | None) -> dict[str, Any]:
    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing kid")
    for key in _load_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    _load_jwks.cache_clear()
    for key in _load_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT signing key not found")


def _decode_supabase_token(token: str) -> dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired Supabase token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise credentials_exception
            key: str | dict[str, Any] = settings.SUPABASE_JWT_SECRET
        else:
            key = _find_jwk(header.get("kid"))

        decode_kwargs: dict[str, Any] = {
            "algorithms": ALGORITHMS,
            "audience": settings.SUPABASE_JWT_AUDIENCE,
            "options": {"verify_aud": True, "verify_iss": bool(_supabase_jwt_issuer())},
        }
        issuer = _supabase_jwt_issuer()
        if issuer:
            decode_kwargs["issuer"] = issuer
        payload = jwt.decode(token, key, **decode_kwargs)
    except (JWTError, ValueError, RuntimeError, HTTPException):
        raise credentials_exception

    sub = payload.get("sub")
    if not sub:
        raise credentials_exception
    try:
        uuid.UUID(str(sub))
    except ValueError:
        raise credentials_exception
    return payload


def _ensure_role(db: Session, role_name: RoleNameEnum) -> Role:
    role = db.query(Role).filter(Role.name == role_name.value).first()
    if role:
        return role
    role = Role(name=role_name.value, description=f"Built-in {role_name.value} role")
    db.add(role)
    db.flush()
    return role


def assign_role(db: Session, user: User, role_name: RoleNameEnum) -> None:
    role = _ensure_role(db, role_name)
    exists = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
        .first()
    )
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id))


def _default_name(payload: dict[str, Any]) -> str:
    metadata = payload.get("user_metadata") or {}
    return metadata.get("name") or metadata.get("full_name") or payload.get("email") or "Supabase user"


def _sync_supabase_profile(db: Session, user: User, payload: dict[str, Any]) -> None:
    """Keep local profile data aligned after identity is linked by Supabase UUID."""
    email = payload.get("email")
    name = _default_name(payload)

    if email and email != user.email:
        conflicting_user = (
            db.query(User)
            .filter(User.email == email, User.id != user.id)
            .first()
        )
        if conflicting_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supabase email is already used by another local user",
            )
        user.email = email

    if name and name != user.name:
        user.name = name


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = _decode_supabase_token(credentials.credentials)
    supabase_user_id = uuid.UUID(str(payload["sub"]))
    email = payload.get("email")

    user = db.query(User).filter(User.supabase_user_id == supabase_user_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()
        if user and user.supabase_user_id is None:
            user.supabase_user_id = supabase_user_id

    if user:
        _sync_supabase_profile(db, user, payload)

    if not user:
        user = User(
            supabase_user_id=supabase_user_id,
            email=email or f"{supabase_user_id}@supabase.local",
            name=_default_name(payload),
        )
        db.add(user)
        db.flush()
        assign_role(db, user, RoleNameEnum.PATIENT)

    db.commit()
    db.refresh(user)
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    try:
        return get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


def get_current_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin privileges required")
    return current_user
