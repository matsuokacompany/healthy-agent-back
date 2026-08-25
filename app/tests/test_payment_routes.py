import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.db.base_class import Base
from app.models.models import Subscription, SubscriptionStatusEnum, User
from app.routes import payment_routes
from app.services.payment_service import PaymentService


def build_app_and_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()

    user = User(name="Paciente", email="paciente@example.com", phone="5511999990000", cpf="12345678900")
    db.add(user)
    db.commit()
    db.refresh(user)

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(payment_routes.router, prefix="/billing")
    app.include_router(payment_routes.webhook_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user

    return TestClient(app), db, user


def test_get_subscription_creates_pending_record_on_first_call():
    client, db, user = build_app_and_db()

    response = client.get("/billing/subscription")

    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 1


def test_checkout_endpoint_returns_service_result(monkeypatch):
    client, db, user = build_app_and_db()
    monkeypatch.setattr(
        PaymentService,
        "start_checkout",
        lambda self, current_user: {"checkout_url": "https://asaas.test/i/abc", "status": "PENDING"},
    )

    response = client.post("/billing/subscription")

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://asaas.test/i/abc", "status": "PENDING"}


def test_webhook_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", "shared-secret")
    client, db, _ = build_app_and_db()

    response = client.post("/webhook/asaas", content=json.dumps({"event": "PAYMENT_CONFIRMED"}))

    assert response.status_code == 403


def test_webhook_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", "shared-secret")
    client, db, _ = build_app_and_db()

    response = client.post(
        "/webhook/asaas",
        content=json.dumps({"event": "PAYMENT_CONFIRMED"}),
        headers={"asaas-access-token": "wrong"},
    )

    assert response.status_code == 403


def test_webhook_accepts_correct_token_and_updates_subscription(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", "shared-secret")
    client, db, user = build_app_and_db()
    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.PENDING.value, provider_subscription_id="sub_123"))
    db.commit()

    response = client.post(
        "/webhook/asaas",
        content=json.dumps({"event": "PAYMENT_CONFIRMED", "payment": {"subscription": "sub_123"}}),
        headers={"asaas-access-token": "shared-secret"},
    )

    assert response.status_code == 204
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).one()
    assert subscription.status == SubscriptionStatusEnum.ACTIVE.value


def test_webhook_returns_500_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", None)
    client, db, _ = build_app_and_db()

    response = client.post(
        "/webhook/asaas",
        content=json.dumps({"event": "PAYMENT_CONFIRMED"}),
        headers={"asaas-access-token": "anything"},
    )

    assert response.status_code == 500
