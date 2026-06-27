from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import secrets

from app.core.dependencies import get_db
from app.models.models import User
from app.core.access_control import (
    AccessContext,
    AuthenticatedContext,
    assert_can_access_context,
    get_default_context,
    get_user_role,
)
from app.core.config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)

oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False
)

# ==================================================
#                   TOKENS
# ==================================================

def create_access_token(user_id: int, active_context: AccessContext | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "exp": int(expire.timestamp()),
    }

    if active_context is not None:
        payload["active_context"] = active_context.value

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return token, expires_at

# ==================================================
#                PASSWORD
# ==================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)

# ==================================================
#                DEPENDENCIES
# ==================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise credentials_exception
        user_id = int(sub)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    return user


def _get_active_context_from_token(token: str) -> AccessContext | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

    raw_context = payload.get("active_context")
    if not raw_context:
        return None

    try:
        return AccessContext(raw_context)
    except ValueError:
        return None


def get_current_auth_context(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
) -> AuthenticatedContext:
    role = get_user_role(current_user)
    active_context = _get_active_context_from_token(token) or get_default_context(role)

    return AuthenticatedContext(
        user=current_user,
        role=role,
        active_context=active_context,
    )


def require_patient_context(
    auth_context: AuthenticatedContext = Depends(get_current_auth_context),
) -> AuthenticatedContext:
    assert_can_access_context(auth_context, AccessContext.PATIENT)
    return auth_context


def require_professional_context(
    auth_context: AuthenticatedContext = Depends(get_current_auth_context),
) -> AuthenticatedContext:
    assert_can_access_context(auth_context, AccessContext.PROFESSIONAL)
    return auth_context


def require_admin_context(
    auth_context: AuthenticatedContext = Depends(get_current_auth_context),
) -> AuthenticatedContext:
    assert_can_access_context(auth_context, AccessContext.ADMIN)
    return auth_context


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            return None
        user_id = int(sub)
    except (JWTError, ValueError):
        return None

    return db.query(User).filter(User.id == user_id).first()

def get_current_admin(
    auth_context: AuthenticatedContext = Depends(require_admin_context),
) -> User:
    return auth_context.user
