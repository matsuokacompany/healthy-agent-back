from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from sqlalchemy.orm import Session

from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    _auth_headers,
    _auth_url,
    _decode_supabase_token,
    _resolve_or_create_user,
    bearer_scheme_optional,
    clear_auth_cookies,
    get_current_user,
    set_auth_cookies,
    set_no_store,
    signup_conflict_error,
    supabase_password_login,
    supabase_refresh,
    supabase_signup,
)
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.document_validation import CnpjLookupError, cnpj_exists
from app.core.rate_limit import limiter
from app.models.models import ProfessionalProfile, User
from app.models.schemas import (
    AuthSessionRead,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfessionalSignupRequest,
    RecoveryExchangeRequest,
    SignupRequest,
    UserRead,
)

router = APIRouter(tags=["Auth"])


def _frontend_allowlist() -> list[str]:
    # A list, not a set: order matters for _default_frontend_origin() below,
    # and a set's iteration order is hash-randomized per process in CPython --
    # picking a "first" entry from one would non-deterministically flip
    # between the dev and production origin on every server restart.
    return [origin.strip().rstrip("/") for origin in settings.AUTH_REDIRECT_ALLOWLIST.split(",") if origin.strip()]


def _default_frontend_origin() -> str | None:
    """The frontend origin to use when no explicit redirect destination is
    given (e.g. building a link for an outbound email, or GET /callback's own
    fallback when it wasn't asked to land anywhere specific) -- prefers a
    non-localhost entry so a dev origin listed alongside the production one
    in AUTH_REDIRECT_ALLOWLIST is never picked as the default in production."""
    origins = _frontend_allowlist()
    non_local = [origin for origin in origins if not origin.startswith("http://localhost")]
    return next(iter(non_local), None) or next(iter(origins), None)


def _allowed_redirect(url: str | None) -> str:
    allowlist = set(_frontend_allowlist())
    fallback = _default_frontend_origin() or "/"
    if not url:
        return fallback
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    if origin.rstrip("/") not in allowlist:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect destination")
    return url


def _session_from_supabase_payload(payload: dict, db: Session) -> User:
    token = payload.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")
    return _resolve_or_create_user(db, _decode_supabase_token(token))


@router.post("/login", response_model=AuthSessionRead)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    set_no_store(response)
    session = supabase_password_login(payload.email, payload.password)
    user = _session_from_supabase_payload(session, db)
    expires_in = int(session.get("expires_in") or 3600)
    set_auth_cookies(
        response,
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_in=expires_in,
    )
    # Tokens are also returned in the body (not just as httponly cookies) for
    # native clients, which have no shared browser cookie jar and authenticate
    # with an `Authorization: Bearer` header instead.
    return AuthSessionRead(
        **UserRead.model_validate(user).model_dump(),
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_in=expires_in,
    )


@router.post("/signup", response_model=UserRead)
@limiter.limit("5/minute")
def signup(request: Request, payload: SignupRequest, response: Response, db: Session = Depends(get_db)):
    """Self-service (no professional involved) account creation.

    Returns 200 with UserRead and sets session cookies if the Supabase
    project auto-confirms new accounts; returns 202 with no cookies if the
    project requires email confirmation first — the browser then completes
    login via the confirmation link, which lands on GET /callback.
    """
    set_no_store(response)
    if db.query(User).filter(User.email == payload.email).first():
        raise signup_conflict_error()
    normalized_phone = "".join(character for character in payload.phone if character.isdigit())
    if normalized_phone and db.query(User).filter(User.phone == normalized_phone).first():
        raise signup_conflict_error()
    # payload.cpf is already digits-only and checksum-validated (see
    # SignupRequest.validate_cpf).
    if db.query(User).filter(User.cpf == payload.cpf).first():
        raise signup_conflict_error()

    # Carried in Supabase's user_metadata (not applied here directly) because
    # e-mail confirmation can defer local row creation to a later request —
    # see _resolve_or_create_user's docstring-level comment for why.
    session = supabase_signup(
        payload.email,
        payload.password,
        metadata={
            "name": payload.name,
            "full_name": payload.name,
            "phone": normalized_phone,
            "city": payload.city,
            "state": payload.state,
            "gender": payload.gender,
            "birth_date": payload.birth_date.isoformat(),
            "cpf": payload.cpf,
            "terms_accepted_at": datetime.now(timezone.utc).isoformat(),
            "terms_version": payload.terms_version,
        },
    )
    if not session.get("access_token"):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "confirmation_email_sent"},
        )

    user = _session_from_supabase_payload(session, db)
    set_auth_cookies(
        response,
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_in=int(session.get("expires_in") or 3600),
    )
    return user


@router.post("/signup-professional", response_model=UserRead)
@limiter.limit("5/minute")
def signup_professional(
    request: Request, payload: ProfessionalSignupRequest, response: Response, db: Session = Depends(get_db)
):
    """Self-service account creation for professionals (parallel to /signup).

    Same 200-with-cookies / 202-pending-confirmation split as /signup — see
    that docstring. New professional accounts start with no billing grace
    (ProfessionalProfile.free_until is NULL): only accounts that already
    existed when professional billing shipped were grandfathered.
    """
    set_no_store(response)
    if db.query(User).filter(User.email == payload.email).first():
        raise signup_conflict_error()
    normalized_phone = "".join(character for character in payload.phone if character.isdigit())
    if normalized_phone and db.query(User).filter(User.phone == normalized_phone).first():
        raise signup_conflict_error()
    # payload.cpf is already digits-only and checksum-validated (see
    # ProfessionalSignupRequest.validate_cpf) — 11 digits means CPF, 14 means CNPJ.
    if db.query(User).filter(User.cpf == payload.cpf).first():
        raise signup_conflict_error()
    if (
        db.query(ProfessionalProfile)
        .filter(
            ProfessionalProfile.license_number == payload.license_number,
            ProfessionalProfile.license_state == payload.license_state,
        )
        .first()
    ):
        raise signup_conflict_error()
    if len(payload.cpf) == 14:
        try:
            if not cnpj_exists(payload.cpf):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CNPJ not found")
        except CnpjLookupError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CNPJ_LOOKUP_UNAVAILABLE")

    session = supabase_signup(
        payload.email,
        payload.password,
        metadata={
            "account_type": "professional",
            "name": payload.name,
            "full_name": payload.name,
            "phone": normalized_phone,
            "cpf": payload.cpf,
            "specialty": payload.specialty,
            "license_number": payload.license_number,
            "license_state": payload.license_state,
            "terms_accepted_at": datetime.now(timezone.utc).isoformat(),
            "terms_version": payload.terms_version,
        },
    )
    if not session.get("access_token"):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "confirmation_email_sent"},
        )

    user = _session_from_supabase_payload(session, db)
    set_auth_cookies(
        response,
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_in=int(session.get("expires_in") or 3600),
    )
    return user


@router.get("/me", response_model=UserRead)
def me(response: Response, current_user: User = Depends(get_current_user)):
    """Return the local domain user resolved from a valid HttpOnly cookie session."""
    set_no_store(response)
    return current_user


@router.get("/csrf")
def csrf_token(request: Request, response: Response):
    """Expose the double-submit token without exposing the HttpOnly session cookies."""
    set_no_store(response)
    token = request.cookies.get(CSRF_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="CSRF token not available")
    response.headers[settings.AUTH_CSRF_HEADER_NAME] = token
    return {"csrf_token": token}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    set_no_store(response)
    # Native clients have no session cookie, so they send the refresh token
    # via this header instead (alongside their — possibly expired —
    # Authorization: Bearer access token, which the CSRF middleware only
    # checks for presence of, not validity, to know this isn't a
    # cookie-authenticated request).
    mobile_refresh_token = request.headers.get("X-Refresh-Token")
    refresh_token = request.cookies.get(REFRESH_COOKIE) or mobile_refresh_token
    if not refresh_token:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        session = supabase_refresh(refresh_token)
        user = _session_from_supabase_payload(session, db)
        next_refresh_token = session.get("refresh_token") or refresh_token
        expires_in = int(session.get("expires_in") or 3600)
        set_auth_cookies(response, access_token=session["access_token"], refresh_token=next_refresh_token, expires_in=expires_in)
    except HTTPException:
        clear_auth_cookies(response)
        raise
    if mobile_refresh_token:
        return AuthSessionRead(
            **UserRead.model_validate(user).model_dump(),
            access_token=session["access_token"],
            refresh_token=next_refresh_token,
            expires_in=expires_in,
        )
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    set_no_store(response)
    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token:
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(_auth_url("/logout"), headers={**_auth_headers(), "Authorization": f"Bearer {access_token}"})
        except Exception:
            pass
    clear_auth_cookies(response)
    return None


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest, response: Response):
    set_no_store(response)
    try:
        # redirect_to is a QUERY parameter here, not a JSON body field --
        # matching invite_supabase_user's already-working /invite call.
        # Confirmed the hard way: sending it in the body (as this and
        # supabase_signup previously did) is silently ignored by Supabase,
        # which falls back to the Site URL -- exactly the symptom that made
        # this fix look like it did nothing on first deploy.
        params: dict = {}
        # Deliberately NOT callback_redirect_to() (GET /callback): that's the
        # right landing spot for signup/invite confirmation -- it logs the
        # user straight into the app -- but for recovery it silently defeats
        # the point, since it drops the browser on the frontend's bare origin,
        # which middleware.ts redirects straight to /login with no chance to
        # set a new password. Recovery must land on the frontend's own
        # /reset-password page, which exchanges the token itself via
        # POST /recovery/exchange below.
        frontend_origin = _default_frontend_origin()
        if frontend_origin:
            params["redirect_to"] = f"{frontend_origin}/reset-password"
        with httpx.Client(timeout=10.0) as client:
            client.post(_auth_url("/recover"), headers=_auth_headers(), params=params, json={"email": payload.email})
    except Exception:
        pass
    return {"message": "If the email exists, password recovery instructions will be sent."}


@router.post("/recovery/exchange", status_code=status.HTTP_204_NO_CONTENT)
def recovery_exchange(payload: RecoveryExchangeRequest, response: Response, db: Session = Depends(get_db)):
    """Establishes a session from a Supabase password-recovery link.

    Called by the frontend's /reset-password page right after it lands there
    (see ResetPasswordPage's prepareRecoverySession) -- distinct from
    GET /callback, which is a full-page redirect target for signup/invite
    confirmation. Recovery instead needs the browser to stay on
    /reset-password so the user can set a new password with
    POST /change-password right after this establishes their session cookies.

    Handles two shapes, since this project's recovery links turned out to use
    the implicit flow (#access_token=...&refresh_token=...) rather than the
    PKCE flow (?code=...) GET /callback expects -- unconfirmed which flow a
    given Supabase project is on without an actual link to test against, so
    this accepts either rather than guessing wrong again.
    """
    set_no_store(response)
    if payload.access_token and payload.refresh_token:
        # Already a Supabase-issued, signed session -- verifying it here is
        # exactly what get_current_user does for any other request; no
        # further call to Supabase is needed to trust it.
        claims = _decode_supabase_token(payload.access_token)
        _resolve_or_create_user(db, claims)
        set_auth_cookies(response, access_token=payload.access_token, refresh_token=payload.refresh_token, expires_in=payload.expires_in or 3600)
        return None
    if not payload.code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Missing recovery code or tokens")
    try:
        with httpx.Client(timeout=10.0) as client:
            supabase_response = client.post(_auth_url("/token?grant_type=pkce"), headers=_auth_headers(), json={"auth_code": payload.code})
    except (httpx.HTTPError, RuntimeError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Recovery exchange failed")
    if supabase_response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired recovery code")
    session = supabase_response.json()
    _session_from_supabase_payload(session, db)
    set_auth_cookies(response, access_token=session["access_token"], refresh_token=session["refresh_token"], expires_in=int(session.get("expires_in") or 3600))
    return None


@router.get("/callback")
def callback(code: str, response: Response, db: Session = Depends(get_db), redirect_to: str | None = None):
    set_no_store(response)
    destination = _allowed_redirect(redirect_to)
    try:
        with httpx.Client(timeout=10.0) as client:
            supabase_response = client.post(_auth_url("/token?grant_type=pkce"), headers=_auth_headers(), json={"auth_code": code})
        if supabase_response.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid callback code")
        session = supabase_response.json()
        _session_from_supabase_payload(session, db)
    except HTTPException:
        raise
    redirect = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    set_no_store(redirect)
    set_auth_cookies(redirect, access_token=session["access_token"], refresh_token=session["refresh_token"], expires_in=int(session.get("expires_in") or 3600))
    return redirect


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
):
    set_no_store(response)
    # Native clients have no session cookie and authenticate with a bearer
    # token instead (see get_current_user) — fall back to it here too.
    access_token = request.cookies.get(ACCESS_COOKIE) or (credentials.credentials if credentials else None)
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    supabase_response = httpx.patch(_auth_url("/user"), headers={**_auth_headers(), "Authorization": f"Bearer {access_token}"}, json={"password": payload.password}, timeout=10.0)
    if supabase_response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")
    return None
