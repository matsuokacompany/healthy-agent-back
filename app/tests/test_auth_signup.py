import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.auth as auth_module
import app.routes.auth_routes as auth_routes_module
from app.core.dependencies import get_db
from app.core.document_validation import CnpjLookupError
from app.core.rate_limit import limiter
from app.db.base_class import Base
from app.models.models import ProfessionalProfile, User
from app.routes import auth_routes


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # @limiter.limit(...) in auth_routes.py closes over the shared `limiter`
    # singleton at import time and enforces via that instance's own storage
    # directly (self._check_request_limit(...)) — it never consults
    # request.app.state.limiter. So counters persist across every test in
    # this file (and module) regardless of what's assigned to app.state;
    # reset the singleton's storage before each test to isolate them.
    limiter.reset()
    yield


def test_callback_redirect_to_uses_api_public_url_not_frontend_allowlist(monkeypatch):
    # Regression test: this previously reused AUTH_REDIRECT_ALLOWLIST (the
    # frontend's origin) to build the link Supabase sends users back to,
    # pointing signup/recovery/invite confirmation emails at a frontend URL
    # that has no /api/auth/callback route.
    from app.core.config import settings

    monkeypatch.setattr(settings, "API_PUBLIC_URL", "https://api.example.com")
    assert auth_module.callback_redirect_to() == "https://api.example.com/api/auth/callback"


def test_callback_redirect_to_is_none_when_not_configured(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "API_PUBLIC_URL", None)
    assert auth_module.callback_redirect_to() is None


class FakeSupabaseSignupResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSupabaseClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        return self._response


def test_supabase_signup_returns_body_on_success(monkeypatch):
    monkeypatch.setattr(auth_module, "_auth_headers", lambda: {})
    monkeypatch.setattr(auth_module, "_auth_url", lambda path: "https://example.supabase.co/auth/v1" + path)
    response = FakeSupabaseSignupResponse(200, {"access_token": "abc", "refresh_token": "def", "expires_in": 3600})
    monkeypatch.setattr(auth_module.httpx, "Client", lambda timeout=10.0: FakeSupabaseClient(response))

    result = auth_module.supabase_signup("a@example.com", "senha-forte-123")

    assert result["access_token"] == "abc"


def test_supabase_signup_raises_conflict_when_user_already_exists(monkeypatch):
    monkeypatch.setattr(auth_module, "_auth_headers", lambda: {})
    monkeypatch.setattr(auth_module, "_auth_url", lambda path: "https://example.supabase.co/auth/v1" + path)
    response = FakeSupabaseSignupResponse(422, {"error_code": "user_already_exists", "msg": "User already registered"})
    monkeypatch.setattr(auth_module.httpx, "Client", lambda timeout=10.0: FakeSupabaseClient(response))

    with pytest.raises(HTTPException) as exc:
        auth_module.supabase_signup("a@example.com", "senha-forte-123")

    assert exc.value.status_code == 409


def test_supabase_signup_does_not_report_conflict_for_unrelated_upstream_failure(monkeypatch):
    # Regression test: a Supabase-side failure unrelated to the email (here,
    # its built-in email sender hitting its own rate limit) must not be
    # reported to the caller as "email already registered" — that was the
    # actual bug that made a transient Supabase outage look like a duplicate
    # signup.
    monkeypatch.setattr(auth_module, "_auth_headers", lambda: {})
    monkeypatch.setattr(auth_module, "_auth_url", lambda path: "https://example.supabase.co/auth/v1" + path)
    response = FakeSupabaseSignupResponse(
        500,
        {"code": 500, "error_code": "unexpected_failure", "msg": "Error sending confirmation email"},
    )
    monkeypatch.setattr(auth_module.httpx, "Client", lambda timeout=10.0: FakeSupabaseClient(response))

    with pytest.raises(HTTPException) as exc:
        auth_module.supabase_signup("a@example.com", "senha-forte-123")

    assert exc.value.status_code == 502


def build_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(auth_routes.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: db

    return TestClient(app), db


def signup_payload(**overrides):
    data = {
        "name": "Paciente Autonomo",
        "email": "autonomo@example.com",
        "password": "senha-forte-123",
        "password_confirmation": "senha-forte-123",
        "phone": "+55 (11) 91234-5678",
        "city": "Londrina",
        "state": "PR",
        "gender": "feminino",
        "birth_date": "1990-05-20",
        "cpf": "111.444.777-35",
        "terms_accepted": True,
        "terms_version": "2026-08-25",
    }
    data.update(overrides)
    return data


def test_signup_rejects_duplicate_email(monkeypatch):
    client, db = build_client()
    db.add(User(name="Existente", email="autonomo@example.com"))
    db.commit()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase for a duplicate email")),
    )

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 409


def test_signup_rejects_duplicate_phone(monkeypatch):
    client, db = build_client()
    db.add(User(name="Existente", email="outro@example.com", phone="5511912345678"))
    db.commit()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase for a duplicate phone")),
    )

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 409


def test_signup_requires_terms_accepted():
    client, _ = build_client()

    response = client.post("/api/auth/signup", json=signup_payload(terms_accepted=False))

    assert response.status_code == 422


def test_signup_rejects_mismatched_password_confirmation():
    client, _ = build_client()

    response = client.post("/api/auth/signup", json=signup_payload(password_confirmation="outra-senha"))

    assert response.status_code == 422


def test_signup_rejects_invalid_cpf_checksum():
    client, _ = build_client()

    response = client.post("/api/auth/signup", json=signup_payload(cpf="123.456.789-00"))

    assert response.status_code == 422


def test_signup_rejects_invalid_ddd():
    client, _ = build_client()

    response = client.post("/api/auth/signup", json=signup_payload(phone="+55 (00) 91234-5678"))

    assert response.status_code == 422


def test_signup_rejects_landline_shaped_phone():
    client, _ = build_client()

    response = client.post("/api/auth/signup", json=signup_payload(phone="+55 (11) 31234-5678"))

    assert response.status_code == 422


def test_signup_with_immediate_session_creates_user_and_sets_cookies(monkeypatch):
    client, db = build_client()
    supabase_user_id = uuid.uuid4()
    # Real Supabase echoes back whatever `data` was sent at signup as
    # user_metadata on the issued JWT — capture it here to verify the
    # metadata round-trip that carries phone/terms through to
    # _resolve_or_create_user, instead of asserting against values that
    # happen to coincidentally match.
    captured_metadata: dict = {}

    def fake_supabase_signup(email, password, metadata=None):
        captured_metadata.update(metadata or {})
        return {"access_token": "fake-access-token", "refresh_token": "fake-refresh-token", "expires_in": 3600}

    monkeypatch.setattr(auth_routes_module, "supabase_signup", fake_supabase_signup)
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {
            "sub": str(supabase_user_id),
            "email": "autonomo@example.com",
            "user_metadata": captured_metadata,
        },
    )

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "autonomo@example.com"
    assert body["roles"] == ["patient"]
    assert "set-cookie" in response.headers or response.cookies

    user = db.query(User).filter(User.email == "autonomo@example.com").one()
    assert user.phone == "5511912345678"
    assert user.supabase_user_id == supabase_user_id
    assert user.terms_version == "2026-08-25"
    assert user.terms_accepted_at is not None
    assert user.city == "Londrina"
    assert user.state == "PR"
    assert user.gender == "feminino"
    assert user.birth_date.isoformat() == "1990-05-20"
    assert user.cpf == "11144477735"


def test_signup_rejects_duplicate_cpf(monkeypatch):
    client, db = build_client()
    db.add(User(name="Existente", email="outro2@example.com", cpf="11144477735"))
    db.commit()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase for a duplicate CPF")),
    )

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 409


def test_signup_without_session_returns_202_and_creates_no_local_user(monkeypatch):
    client, db = build_client()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda email, password, metadata=None: {"user": {"id": "some-id"}},
    )

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 202
    assert response.json()["message"] == "confirmation_email_sent"
    assert db.query(User).count() == 0


def test_signup_phone_and_terms_survive_deferred_confirmation_then_login(monkeypatch):
    # End-to-end regression test for the exact bug reported in production:
    # signup requires e-mail confirmation (202, no local row yet), and the
    # account only actually materializes later — here, via a plain login —
    # through _resolve_or_create_user. phone/terms must still be applied.
    client, db = build_client()
    captured_metadata: dict = {}

    def fake_supabase_signup(email, password, metadata=None):
        captured_metadata.update(metadata or {})
        return {"user": {"id": "some-id"}}  # no access_token: confirmation required

    monkeypatch.setattr(auth_routes_module, "supabase_signup", fake_supabase_signup)

    signup_response = client.post("/api/auth/signup", json=signup_payload())
    assert signup_response.status_code == 202
    assert db.query(User).count() == 0

    supabase_user_id = uuid.uuid4()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_password_login",
        lambda email, password: {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
    )
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {"sub": str(supabase_user_id), "email": "autonomo@example.com", "user_metadata": captured_metadata},
    )

    login_response = client.post("/api/auth/login", json={"email": "autonomo@example.com", "password": "senha-forte-123"})

    assert login_response.status_code == 200
    user = db.query(User).filter(User.email == "autonomo@example.com").one()
    assert user.phone == "5511912345678"
    assert user.terms_version == "2026-08-25"
    assert user.terms_accepted_at is not None
    assert user.cpf == "11144477735"
    assert user.birth_date.isoformat() == "1990-05-20"


def professional_signup_payload(**overrides):
    data = {
        "name": "Dr. Autonomo",
        "email": "profissional-autonomo@example.com",
        "password": "senha-forte-123",
        "password_confirmation": "senha-forte-123",
        "phone": "+55 (11) 91234-5678",
        "cpf": "111.444.777-35",
        "specialty": "Nutrição",
        "license_number": "CRN-12345",
        "license_state": "PR",
        "terms_accepted": True,
        "terms_version": "2026-08-25",
    }
    data.update(overrides)
    return data


def test_signup_professional_creates_professional_role_and_profile(monkeypatch):
    client, db = build_client()
    supabase_user_id = uuid.uuid4()
    captured_metadata: dict = {}

    def fake_supabase_signup(email, password, metadata=None):
        captured_metadata.update(metadata or {})
        return {"access_token": "fake-access-token", "refresh_token": "fake-refresh-token", "expires_in": 3600}

    monkeypatch.setattr(auth_routes_module, "supabase_signup", fake_supabase_signup)
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {
            "sub": str(supabase_user_id),
            "email": "profissional-autonomo@example.com",
            "user_metadata": captured_metadata,
        },
    )

    response = client.post("/api/auth/signup-professional", json=professional_signup_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["professional"]

    user = db.query(User).filter(User.email == "profissional-autonomo@example.com").one()
    profile = db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == user.id).one()
    assert profile.specialty == "Nutrição"
    assert profile.license_number == "CRN-12345"
    assert profile.license_state == "PR"
    assert profile.free_until is None, "new self-signups get no billing grace period"


def test_signup_professional_rejects_mismatched_password_confirmation():
    client, _ = build_client()

    response = client.post(
        "/api/auth/signup-professional",
        json=professional_signup_payload(password_confirmation="outra-senha"),
    )

    assert response.status_code == 422


def test_signup_professional_rejects_invalid_cpf_checksum():
    client, _ = build_client()

    response = client.post("/api/auth/signup-professional", json=professional_signup_payload(cpf="123.456.789-00"))

    assert response.status_code == 422


def test_signup_professional_rejects_invalid_cnpj_checksum():
    client, _ = build_client()

    response = client.post(
        "/api/auth/signup-professional",
        json=professional_signup_payload(cpf="11.222.333/0001-99"),
    )

    assert response.status_code == 422


def test_signup_professional_accepts_cnpj_verified_to_exist(monkeypatch):
    client, db = build_client()
    supabase_user_id = uuid.uuid4()
    captured_metadata: dict = {}

    def fake_supabase_signup(email, password, metadata=None):
        captured_metadata.update(metadata or {})
        return {"access_token": "fake-access-token", "refresh_token": "fake-refresh-token", "expires_in": 3600}

    monkeypatch.setattr(auth_routes_module, "cnpj_exists", lambda digits: True)
    monkeypatch.setattr(auth_routes_module, "supabase_signup", fake_supabase_signup)
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {
            "sub": str(supabase_user_id),
            "email": "clinica-autonoma@example.com",
            "user_metadata": captured_metadata,
        },
    )

    response = client.post(
        "/api/auth/signup-professional",
        json=professional_signup_payload(email="clinica-autonoma@example.com", cpf="11.222.333/0001-81"),
    )

    assert response.status_code == 200
    user = db.query(User).filter(User.email == "clinica-autonoma@example.com").one()
    assert user.cpf == "11222333000181"


def test_signup_professional_rejects_cnpj_not_found(monkeypatch):
    client, _ = build_client()
    monkeypatch.setattr(auth_routes_module, "cnpj_exists", lambda digits: False)
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase for a nonexistent CNPJ")),
    )

    response = client.post(
        "/api/auth/signup-professional",
        json=professional_signup_payload(cpf="11.222.333/0001-81"),
    )

    assert response.status_code == 422


def test_signup_professional_returns_503_when_cnpj_lookup_unavailable(monkeypatch):
    client, _ = build_client()

    def raise_lookup_error(digits):
        raise CnpjLookupError("boom")

    monkeypatch.setattr(auth_routes_module, "cnpj_exists", raise_lookup_error)
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase when CNPJ lookup fails")),
    )

    response = client.post(
        "/api/auth/signup-professional",
        json=professional_signup_payload(cpf="11.222.333/0001-81"),
    )

    assert response.status_code == 503


def test_signup_professional_rejects_duplicate_license(monkeypatch):
    client, db = build_client()
    existing_user = User(name="Existente", email="outro-profissional@example.com")
    db.add(existing_user)
    db.flush()
    db.add(ProfessionalProfile(user_id=existing_user.id, license_number="CRN-12345", license_state="PR", active=True))
    db.commit()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase for a duplicate license")),
    )

    response = client.post("/api/auth/signup-professional", json=professional_signup_payload())

    assert response.status_code == 409


def test_signup_professional_rejects_duplicate_email(monkeypatch):
    client, db = build_client()
    db.add(User(name="Existente", email="profissional-autonomo@example.com"))
    db.commit()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Supabase for a duplicate email")),
    )

    response = client.post("/api/auth/signup-professional", json=professional_signup_payload())

    assert response.status_code == 409
