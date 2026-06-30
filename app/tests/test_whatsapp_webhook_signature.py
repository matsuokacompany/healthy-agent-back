import hashlib
import hmac

import pytest
from fastapi import HTTPException, status

from app.core.config import settings
from app.routes.bot_webhook_routes import verify_whatsapp_signature


def make_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_whatsapp_signature_accepts_valid_signature(monkeypatch):
    body = b'{"object":"whatsapp_business_account"}'
    secret = "meta-app-secret"
    monkeypatch.setattr(settings, "APP_SECRET", secret)

    verify_whatsapp_signature(body, make_signature(secret, body))


def test_verify_whatsapp_signature_rejects_invalid_signature(monkeypatch):
    body = b'{"object":"whatsapp_business_account"}'
    monkeypatch.setattr(settings, "APP_SECRET", "meta-app-secret")

    with pytest.raises(HTTPException) as exc:
        verify_whatsapp_signature(body, "sha256=invalid")

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_verify_whatsapp_signature_rejects_missing_signature(monkeypatch):
    monkeypatch.setattr(settings, "APP_SECRET", "meta-app-secret")

    with pytest.raises(HTTPException) as exc:
        verify_whatsapp_signature(b"{}", None)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_verify_whatsapp_signature_fails_closed_when_secret_is_missing(monkeypatch):
    monkeypatch.setattr(settings, "APP_SECRET", None)

    with pytest.raises(HTTPException) as exc:
        verify_whatsapp_signature(b"{}", "sha256=anything")

    assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
