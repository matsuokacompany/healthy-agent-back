from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.auth import _decode_supabase_token, _supabase_jwt_issuer
from app.core.config import settings


def make_token(secret, project_url, *, sub=None, aud="authenticated", iss=None):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(sub or uuid.uuid4()),
            "email": "user@example.com",
            "aud": aud,
            "iss": iss or f"{project_url}/auth/v1",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "user_metadata": {"name": "Test User"},
        },
        secret,
        algorithm="HS256",
    )


def configure_supabase(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_PROJECT_URL", "https://project-ref.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "supabase-test-secret")
    monkeypatch.setattr(settings, "SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr(settings, "SUPABASE_JWT_ISSUER", None)


def test_supabase_issuer_is_derived_from_project_url(monkeypatch):
    configure_supabase(monkeypatch)

    assert _supabase_jwt_issuer() == "https://project-ref.supabase.co/auth/v1"


def test_decode_supabase_hs256_token_validates_secret_issuer_audience_and_sub(monkeypatch):
    configure_supabase(monkeypatch)
    supabase_user_id = uuid.uuid4()
    token = make_token(
        settings.SUPABASE_JWT_SECRET,
        settings.SUPABASE_PROJECT_URL,
        sub=supabase_user_id,
    )

    payload = _decode_supabase_token(token)

    assert payload["sub"] == str(supabase_user_id)
    assert payload["aud"] == "authenticated"
    assert payload["iss"] == "https://project-ref.supabase.co/auth/v1"


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "anon"},
        {"iss": "https://wrong-project.supabase.co/auth/v1"},
        {"sub": "not-a-uuid"},
    ],
)
def test_decode_supabase_hs256_token_rejects_invalid_required_claims(monkeypatch, claims):
    configure_supabase(monkeypatch)
    token = make_token(
        settings.SUPABASE_JWT_SECRET,
        settings.SUPABASE_PROJECT_URL,
        **claims,
    )

    with pytest.raises(HTTPException) as exc:
        _decode_supabase_token(token)

    assert exc.value.status_code == 401
