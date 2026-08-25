import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routes.auth_routes as auth_routes_module
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.db.base_class import Base
from app.models.models import User
from app.routes import auth_routes


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
        "phone": "+55 (11) 91234-5678",
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


def test_signup_with_immediate_session_creates_user_and_sets_cookies(monkeypatch):
    client, db = build_client()
    supabase_user_id = uuid.uuid4()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda email, password, name=None: {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        auth_routes_module,
        "_decode_supabase_token",
        lambda token: {
            "sub": str(supabase_user_id),
            "email": "autonomo@example.com",
            "user_metadata": {"name": "Paciente Autonomo"},
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


def test_signup_without_session_returns_202_and_creates_no_local_user(monkeypatch):
    client, db = build_client()
    monkeypatch.setattr(
        auth_routes_module,
        "supabase_signup",
        lambda email, password, name=None: {"user": {"id": "some-id"}},
    )

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 202
    assert response.json()["message"] == "confirmation_email_sent"
    assert db.query(User).count() == 0
