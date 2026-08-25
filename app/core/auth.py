from datetime import datetime, timezone
from functools import lru_cache
import logging
import traceback
from typing import Any
from urllib.request import urlopen
import json
import uuid

import secrets
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.permissions import has_role, is_admin, is_super_admin
from app.core.user_identity import is_email_like
from app.db.security_context import set_database_identity_context
from app.models.models import Role, RoleNameEnum, User, UserRole

ALGORITHMS = ["HS256", "RS256", "ES256"]

bearer_scheme = HTTPBearer()
bearer_scheme_optional = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

ACCESS_COOKIE = settings.AUTH_ACCESS_COOKIE_NAME
REFRESH_COOKIE = settings.AUTH_REFRESH_COOKIE_NAME
CSRF_COOKIE = settings.AUTH_CSRF_COOKIE_NAME
CSRF_HEADER = settings.AUTH_CSRF_HEADER_NAME
REFRESH_COOKIE_PATH = "/"
LEGACY_REFRESH_COOKIE_PATH = "/api/auth"


def _auth_headers() -> dict[str, str]:
    if not settings.SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_ANON_KEY must be configured for Supabase Auth server-side calls")
    return {"apikey": settings.SUPABASE_ANON_KEY, "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}"}


def _auth_url(path: str) -> str:
    project_url = _supabase_project_url()
    if not project_url:
        raise RuntimeError("SUPABASE_PROJECT_URL must be configured")
    return f"{project_url}/auth/v1{path}"


def _generic_auth_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


def set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str, expires_in: int) -> str:
    csrf_token = secrets.token_urlsafe(32)
    secure = settings.AUTH_COOKIE_SECURE
    same_site = settings.AUTH_COOKIE_SAMESITE.lower()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=max(1, int(expires_in)),
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=secure,
        samesite="strict",
        # The default name uses the __Host- prefix. Browsers only accept a
        # __Host- cookie when Path=/ (and no Domain is present). Using the
        # narrower /api/auth path silently discarded the refresh cookie in
        # compliant browsers and ended the session when the access JWT expired.
        path=REFRESH_COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=60 * 60 * 24 * 30,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.headers[CSRF_HEADER] = csrf_token
    return csrf_token


def clear_auth_cookies(response: Response) -> None:
    secure = settings.AUTH_COOKIE_SECURE
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=secure, samesite=settings.AUTH_COOKIE_SAMESITE.lower())
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, secure=secure, samesite="strict")
    # Also expire cookies created by deployments that used a custom (non
    # __Host-) name with the former path.
    response.delete_cookie(REFRESH_COOKIE, path=LEGACY_REFRESH_COOKIE_PATH, secure=secure, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="strict")


def _resolve_or_create_user(db: Session, payload: dict[str, Any]) -> User:
    supabase_user_id = uuid.UUID(str(payload["sub"]))
    email = payload.get("email") or "unknown@example.com"
    set_database_identity_context(db, supabase_user_id, email)
    user = db.query(User).filter(User.supabase_user_id == supabase_user_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()
        if user and user.supabase_user_id is None:
            user.supabase_user_id = supabase_user_id
    if not user:
        user = User(email=email, name=email.split("@")[0], supabase_user_id=supabase_user_id)
        db.add(user)
        db.flush()
        assign_role(db, user, RoleNameEnum.PATIENT)
    elif not user.role_records:
        # Legacy/pre-provisioned records may have an identity but no application
        # role. Authentication succeeded in that case, but clients could not
        # choose an access context. Give only the least-privileged role here;
        # professional and administrative roles still require provisioning.
        assign_role(db, user, RoleNameEnum.PATIENT)
    _sync_supabase_profile(db, user, payload)
    db.commit()
    # commit ends SET LOCAL; rebind the identity for route queries that reuse
    # this FastAPI dependency-scoped session.
    set_database_identity_context(db, supabase_user_id, email)
    db.refresh(user)
    return user


def supabase_password_login(email: str, password: str) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                _auth_url("/token?grant_type=password"),
                headers=_auth_headers(),
                json={"email": email, "password": password},
            )
    except (httpx.HTTPError, RuntimeError):
        logger.info("Supabase login failed for email=%s", email)
        raise _generic_auth_error()
    if response.status_code >= 400:
        logger.info("Supabase login rejected for email=%s status=%s", email, response.status_code)
        raise _generic_auth_error()
    return response.json()


def supabase_signup(email: str, password: str, *, name: str | None = None) -> dict[str, Any]:
    """Create a new Supabase Auth user via the public /signup endpoint (anon key).

    Returns Supabase's response body. If the project auto-confirms new users,
    the body includes a session with access_token/refresh_token, ready to be
    exchanged into our own cookies exactly like login. If the project requires
    email confirmation, the body has a user but no session — the caller must
    handle that case (no local session can be established yet).
    """
    body: dict[str, Any] = {"email": email, "password": password}
    if name:
        body["data"] = {"name": name}
    # Without this, the confirmation email (when the project requires one)
    # links back to Supabase's default Site URL instead of our callback,
    # same reasoning as forgot_password's redirect_to in auth_routes.py.
    allowlist = [origin.strip().rstrip("/") for origin in settings.AUTH_REDIRECT_ALLOWLIST.split(",") if origin.strip()]
    if allowlist:
        body["redirect_to"] = f"{allowlist[0]}/api/auth/callback"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(_auth_url("/signup"), headers=_auth_headers(), json=body)
    except (httpx.HTTPError, RuntimeError):
        logger.info("Supabase signup request failed for email=%s", email)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Signup failed")
    if response.status_code >= 400:
        # Log the body (never the password) so a genuine upstream failure —
        # e.g. Supabase's built-in email sender returning
        # {"error_code": "unexpected_failure", "msg": "Error sending
        # confirmation email"} once its low default rate limit is hit — is
        # diagnosable instead of being reported to the user as a duplicate
        # email, which it may not be at all.
        error_payload = response.json() if "application/json" in response.headers.get("content-type", "") else {}
        logger.warning(
            "Supabase signup rejected for email=%s status=%s body=%s",
            email,
            response.status_code,
            error_payload or response.text[:500],
        )
        error_code = str(error_payload.get("error_code") or "")
        message = str(error_payload.get("msg") or error_payload.get("error_description") or "")
        if error_code == "user_already_exists" or "already registered" in message.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Signup is temporarily unavailable. Please try again shortly.",
        )
    return response.json()


def supabase_refresh(refresh_token: str) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                _auth_url("/token?grant_type=refresh_token"),
                headers=_auth_headers(),
                json={"refresh_token": refresh_token},
            )
    except (httpx.HTTPError, RuntimeError):
        raise _generic_auth_error()
    if response.status_code >= 400:
        raise _generic_auth_error()
    return response.json()


def _admin_headers() -> dict[str, str]:
    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be configured for Supabase Auth admin calls")
    return {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }


def invite_supabase_user(email: str, *, name: str | None = None) -> uuid.UUID | None:
    """Create a Supabase Auth user for a pre-provisioned local record and email them an invite.

    Best-effort: a pre-provisioned patient still works without a linked Supabase
    identity (self-signup with the same email links it later via
    `_resolve_or_create_user`), so any failure here is logged and swallowed
    rather than blocking patient provisioning on Supabase Auth availability.
    """
    project_url = _supabase_project_url()
    if not project_url or not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("Skipping Supabase invite for email=%s: Supabase Auth admin not configured", email)
        return None

    allowlist = [origin.strip().rstrip("/") for origin in settings.AUTH_REDIRECT_ALLOWLIST.split(",") if origin.strip()]
    redirect_to = f"{allowlist[0]}/api/auth/callback" if allowlist else None
    body: dict[str, Any] = {"email": email}
    if name:
        body["data"] = {"name": name}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{project_url}/auth/v1/invite",
                headers=_admin_headers(),
                params={"redirect_to": redirect_to} if redirect_to else None,
                json=body,
            )
    except (httpx.HTTPError, RuntimeError):
        logger.warning("Supabase invite request failed for email=%s", email)
        return None
    if response.status_code >= 400:
        logger.warning("Supabase invite rejected for email=%s status=%s", email, response.status_code)
        return None

    invited_id = response.json().get("id")
    if not invited_id:
        return None
    try:
        return uuid.UUID(str(invited_id))
    except ValueError:
        return None


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


def _metadata_name(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("user_metadata") or {}
    name = metadata.get("name") or metadata.get("full_name")
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or is_email_like(name):
        return None
    return name


def _log_user_update(user: User, *, previous_name: str | None, new_name: str | None, origin: str) -> None:
    logger.warning(
        "Updating public.users user_id=%s previous_name=%r new_name=%r origin=%s stack=%s",
        user.id,
        previous_name,
        new_name,
        origin,
        "".join(traceback.format_stack(limit=8)),
    )


def _sync_supabase_profile(db: Session, user: User, payload: dict[str, Any]) -> None:
    """Keep local profile data aligned after identity is linked by Supabase UUID."""
    email = payload.get("email")
    metadata_name = _metadata_name(payload)

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
        _log_user_update(
            user,
            previous_name=user.name,
            new_name=user.name,
            origin="auth._sync_supabase_profile.email",
        )
        user.email = email

    if metadata_name and metadata_name != user.name:
        _log_user_update(
            user,
            previous_name=user.name,
            new_name=metadata_name,
            origin="auth._sync_supabase_profile.name",
        )
        user.name = metadata_name


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(ACCESS_COOKIE) or (credentials.credentials if credentials else None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return _resolve_or_create_user(db, _decode_supabase_token(token))


def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials and not request.cookies.get(ACCESS_COOKIE):
        return None
    try:
        return get_current_user(request=request, credentials=credentials, db=db)
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


def get_current_professional_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_admin(current_user) and not has_role(current_user, RoleNameEnum.PROFESSIONAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional or admin privileges required",
        )
    return current_user
