from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from sqlalchemy.orm import Session

from app.core.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    _auth_headers,
    _auth_url,
    _decode_supabase_token,
    _resolve_or_create_user,
    callback_redirect_to,
    clear_auth_cookies,
    get_current_user,
    set_auth_cookies,
    set_no_store,
    supabase_password_login,
    supabase_refresh,
    supabase_signup,
)
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.models.models import ProfessionalProfile, User
from app.models.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfessionalSignupRequest,
    SignupRequest,
    UserRead,
)

router = APIRouter(tags=["Auth"])


def _allowed_redirect(url: str | None) -> str:
    allowlist = {origin.strip().rstrip("/") for origin in settings.AUTH_REDIRECT_ALLOWLIST.split(",") if origin.strip()}
    fallback = next(iter(allowlist), "/")
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


@router.post("/login", response_model=UserRead)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    set_no_store(response)
    session = supabase_password_login(payload.email, payload.password)
    user = _session_from_supabase_payload(session, db)
    set_auth_cookies(
        response,
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_in=int(session.get("expires_in") or 3600),
    )
    return user


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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    normalized_phone = "".join(character for character in payload.phone if character.isdigit())
    if normalized_phone and db.query(User).filter(User.phone == normalized_phone).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone already registered")
    normalized_cpf = "".join(character for character in payload.cpf if character.isdigit())
    if normalized_cpf and db.query(User).filter(User.cpf == normalized_cpf).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CPF already registered")

    # Carried in Supabase's user_metadata (not applied here directly) because
    # e-mail confirmation can defer local row creation to a later request —
    # see _resolve_or_create_user's docstring-level comment for why.
    session = supabase_signup(
        payload.email,
        payload.password,
        metadata={
            "name": payload.name,
            "phone": normalized_phone,
            "city": payload.city,
            "state": payload.state,
            "gender": payload.gender,
            "birth_date": payload.birth_date.isoformat(),
            "cpf": normalized_cpf,
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    normalized_phone = "".join(character for character in payload.phone if character.isdigit())
    if normalized_phone and db.query(User).filter(User.phone == normalized_phone).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone already registered")
    normalized_cpf = "".join(character for character in payload.cpf if character.isdigit())
    if normalized_cpf and db.query(User).filter(User.cpf == normalized_cpf).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CPF already registered")
    if (
        db.query(ProfessionalProfile)
        .filter(
            ProfessionalProfile.license_number == payload.license_number,
            ProfessionalProfile.license_state == payload.license_state,
        )
        .first()
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="License already registered")

    session = supabase_signup(
        payload.email,
        payload.password,
        metadata={
            "account_type": "professional",
            "name": payload.name,
            "phone": normalized_phone,
            "cpf": normalized_cpf,
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


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    set_no_store(response)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        session = supabase_refresh(refresh_token)
        _session_from_supabase_payload(session, db)
        set_auth_cookies(
            response,
            access_token=session["access_token"],
            refresh_token=session.get("refresh_token") or refresh_token,
            expires_in=int(session.get("expires_in") or 3600),
        )
    except HTTPException:
        clear_auth_cookies(response)
        raise
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
        body: dict = {"email": payload.email}
        redirect_to = callback_redirect_to()
        if redirect_to:
            body["redirect_to"] = redirect_to
        with httpx.Client(timeout=10.0) as client:
            client.post(_auth_url("/recover"), headers=_auth_headers(), json=body)
    except Exception:
        pass
    return {"message": "If the email exists, password recovery instructions will be sent."}


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
def change_password(payload: ChangePasswordRequest, request: Request, response: Response, current_user: User = Depends(get_current_user)):
    set_no_store(response)
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    supabase_response = httpx.patch(_auth_url("/user"), headers={**_auth_headers(), "Authorization": f"Bearer {access_token}"}, json={"password": payload.password}, timeout=10.0)
    if supabase_response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")
    return None
