import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routes.auth_routes as auth_routes_module
from app.core.auth import ACCESS_COOKIE
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.db.base_class import Base
from app.models.models import User
from app.routes import auth_routes


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield


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


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class RecordingFakeClient:
    """Captures every POST call's url/json for assertions, and returns
    canned responses in call order."""

    def __init__(self, calls, responses):
        self.calls = calls
        self._responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None, params=None):
        self.calls.append({"url": url, "json": json, "params": params})
        return self._responses.pop(0)


def test_forgot_password_redirects_recovery_to_frontend_reset_password_page(monkeypatch):
    # Regression test: recovery must NOT reuse callback_redirect_to() (the
    # generic GET /api/auth/callback used for signup/invite confirmation) --
    # that logs the user straight into the app and drops them on the
    # frontend's bare origin, which middleware.ts redirects straight to
    # /login, with no chance to actually set a new password.
    client, _ = build_client()
    calls: list[dict] = []
    monkeypatch.setattr(auth_routes_module, "_auth_headers", lambda: {})
    monkeypatch.setattr(auth_routes_module, "_auth_url", lambda path: "https://example.supabase.co/auth/v1" + path)
    monkeypatch.setattr(auth_routes_module.httpx, "Client", lambda timeout=10.0: RecordingFakeClient(calls, [FakeResponse(200, {})]))

    response = client.post("/api/auth/forgot-password", json={"email": "paciente@example.com"})

    assert response.status_code == 202
    assert len(calls) == 1
    # Regression test: redirect_to is a QUERY parameter, not a body field --
    # confirmed against a real recovery click that landed on the Site URL
    # instead, because Supabase silently ignores it in the JSON body.
    assert calls[0]["params"] == {"redirect_to": "https://app.julha.com.br/reset-password"}
    assert "redirect_to" not in calls[0]["json"]


def test_recovery_exchange_creates_session_and_local_user(monkeypatch):
    client, db = build_client()
    supabase_user_id = uuid.uuid4()
    calls: list[dict] = []
    token_response = FakeResponse(200, {"access_token": "recovery-access-token", "refresh_token": "recovery-refresh-token", "expires_in": 3600})
    monkeypatch.setattr(auth_routes_module, "_auth_headers", lambda: {})
    monkeypatch.setattr(auth_routes_module, "_auth_url", lambda path: "https://example.supabase.co/auth/v1" + path)
    monkeypatch.setattr(auth_routes_module.httpx, "Client", lambda timeout=10.0: RecordingFakeClient(calls, [token_response]))
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {"sub": str(supabase_user_id), "email": "recuperando@example.com", "user_metadata": {}},
    )

    response = client.post("/api/auth/recovery/exchange", json={"code": "some-pkce-code"})

    assert response.status_code == 204
    assert ACCESS_COOKIE in response.cookies
    assert calls[0]["json"] == {"auth_code": "some-pkce-code"}

    user = db.query(User).filter(User.email == "recuperando@example.com").one()
    assert user.supabase_user_id == supabase_user_id


def test_recovery_exchange_accepts_implicit_flow_tokens(monkeypatch):
    # This Supabase project turned out to issue implicit-flow recovery links
    # (#access_token=...&refresh_token=...) rather than the PKCE ?code= flow
    # GET /callback expects -- confirmed against a real recovery link.
    client, db = build_client()
    supabase_user_id = uuid.uuid4()
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {"sub": str(supabase_user_id), "email": "recuperando@example.com", "user_metadata": {}},
    )

    response = client.post(
        "/api/auth/recovery/exchange",
        json={"access_token": "implicit-access-token", "refresh_token": "implicit-refresh-token", "expires_in": 3600},
    )

    assert response.status_code == 204
    assert ACCESS_COOKIE in response.cookies
    user = db.query(User).filter(User.email == "recuperando@example.com").one()
    assert user.supabase_user_id == supabase_user_id


def test_recovery_exchange_requires_code_or_tokens(monkeypatch):
    client, _ = build_client()

    response = client.post("/api/auth/recovery/exchange", json={})

    assert response.status_code == 422


def test_default_frontend_origin_prefers_non_localhost_deterministically(monkeypatch):
    # Regression test: the previous implementation picked a "first" entry
    # from a set built out of AUTH_REDIRECT_ALLOWLIST -- a set's iteration
    # order is hash-randomized per process in CPython, so this could
    # non-deterministically resolve to the dev origin (localhost:3000) in
    # production on any given server restart, for both this recovery
    # redirect and GET /callback's own fallback destination.
    monkeypatch.setattr(auth_routes_module.settings, "AUTH_REDIRECT_ALLOWLIST", "http://localhost:3000,https://app.julha.com.br")
    for _ in range(20):
        assert auth_routes_module._default_frontend_origin() == "https://app.julha.com.br"


def test_recovery_exchange_rejects_invalid_or_expired_code(monkeypatch):
    client, _ = build_client()
    calls: list[dict] = []
    monkeypatch.setattr(auth_routes_module, "_auth_headers", lambda: {})
    monkeypatch.setattr(auth_routes_module, "_auth_url", lambda path: "https://example.supabase.co/auth/v1" + path)
    monkeypatch.setattr(auth_routes_module.httpx, "Client", lambda timeout=10.0: RecordingFakeClient(calls, [FakeResponse(400, {"error_code": "otp_expired"})]))

    response = client.post("/api/auth/recovery/exchange", json={"code": "expired-code"})

    assert response.status_code == 401
