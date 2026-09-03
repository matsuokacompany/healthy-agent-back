from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.auth import get_current_user
from app.core.rate_limit import limiter
from app.models.models import User
from app.routes import support_routes


def build_app(current_user):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(support_routes.router, prefix="/support")
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def build_user():
    return User(id=1, name="Maria Paciente", email="maria@example.com")


def test_send_support_contact_emails_the_support_inbox(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.support_service.send_email", lambda **kwargs: calls.append(kwargs) or True)
    client = build_app(build_user())

    response = client.post("/support/contact", data={"subject": "Problema técnico", "message": "A tela trava."})

    assert response.status_code == 204
    assert len(calls) == 1
    assert calls[0]["to"]
    assert "A tela trava." in calls[0]["body"]


def test_send_support_contact_accepts_an_image_attachment(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.support_service.send_email", lambda **kwargs: calls.append(kwargs) or True)
    client = build_app(build_user())

    response = client.post(
        "/support/contact",
        data={"subject": "Dúvida", "message": "Segue print."},
        files={"attachment": ("print.png", b"fake-bytes", "image/png")},
    )

    assert response.status_code == 204
    assert calls[0]["attachment"] == (b"fake-bytes", "print.png", "image/png")


def test_send_support_contact_rejects_unsupported_attachment_type(monkeypatch):
    monkeypatch.setattr("app.services.support_service.send_email", lambda **kwargs: True)
    client = build_app(build_user())

    response = client.post(
        "/support/contact",
        data={"subject": "Dúvida", "message": "Segue arquivo."},
        files={"attachment": ("documento.pdf", b"fake-bytes", "application/pdf")},
    )

    assert response.status_code == 415


def test_send_support_contact_requires_a_message():
    client = build_app(build_user())

    response = client.post("/support/contact", data={"subject": "Dúvida", "message": ""})

    assert response.status_code == 422


def test_send_support_contact_surfaces_delivery_failure(monkeypatch):
    monkeypatch.setattr("app.services.support_service.send_email", lambda **kwargs: False)
    client = build_app(build_user())

    response = client.post("/support/contact", data={"subject": "Problema técnico", "message": "Não consigo entrar."})

    assert response.status_code == 502
