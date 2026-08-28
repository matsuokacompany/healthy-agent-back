import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_super_admin, get_current_user
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
        lambda self, current_user, plan_id: {
            "checkout_url": "https://asaas.test/i/abc",
            "status": "PENDING",
            "plan_id": plan_id,
        },
    )

    response = client.post("/billing/subscription", json={"plan_id": "monthly"})

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://asaas.test/i/abc", "status": "PENDING", "plan_id": "monthly"}


def test_list_plans_returns_configured_plans(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", 1990)
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS", None)
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_ANNUAL_PRICE_CENTS", None)
    client, _, _ = build_app_and_db()

    response = client.get("/billing/plans")

    assert response.status_code == 200
    body = response.json()
    assert [plan["id"] for plan in body] == ["monthly"]
    assert body[0]["price_cents"] == 1990


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


def test_cancel_endpoint_delegates_to_service(monkeypatch):
    client, db, user = build_app_and_db()
    monkeypatch.setattr(
        PaymentService,
        "cancel_subscription",
        lambda self, current_user: Subscription(user_id=current_user.id, status=SubscriptionStatusEnum.ACTIVE.value, cancel_at_period_end=True),
    )

    response = client.post("/billing/subscription/cancel")

    assert response.status_code == 200
    assert response.json()["cancel_at_period_end"] is True


def test_refund_endpoint_delegates_to_service(monkeypatch):
    client, db, user = build_app_and_db()
    monkeypatch.setattr(
        PaymentService,
        "refund_subscription",
        lambda self, current_user: Subscription(user_id=current_user.id, status=SubscriptionStatusEnum.CANCELED.value, cancel_at_period_end=False),
    )

    response = client.post("/billing/subscription/refund")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELED"


def test_refund_endpoint_surfaces_service_error(monkeypatch):
    from fastapi import HTTPException, status

    client, db, user = build_app_and_db()

    def raise_expired(self, current_user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="REFUND_WINDOW_EXPIRED")

    monkeypatch.setattr(PaymentService, "refund_subscription", raise_expired)

    response = client.post("/billing/subscription/refund")

    assert response.status_code == 409
    assert response.json()["detail"] == "REFUND_WINDOW_EXPIRED"


def _deny_super_admin():
    raise HTTPException(status_code=403, detail="Super admin privileges required")


def test_admin_grant_trial_requires_super_admin():
    client, db, user = build_app_and_db()
    client.app.dependency_overrides[get_current_super_admin] = _deny_super_admin

    response = client.post(f"/billing/admin/subscriptions/{user.id}/grant-trial", json={"days": 14})

    assert response.status_code == 403


def test_admin_grant_trial_sets_trialing_status_without_touching_asaas():
    client, db, user = build_app_and_db()
    admin = User(name="Admin", email="admin@example.com")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.app.dependency_overrides[get_current_super_admin] = lambda: admin

    response = client.post(f"/billing/admin/subscriptions/{user.id}/grant-trial", json={"days": 14})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "TRIALING"
    assert body["trial_ends_at"] is not None
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).one()
    assert subscription.provider_subscription_id is None


def test_admin_grant_trial_404_for_unknown_user():
    client, db, admin_user = build_app_and_db()
    client.app.dependency_overrides[get_current_super_admin] = lambda: admin_user

    response = client.post("/billing/admin/subscriptions/999999/grant-trial", json={"days": 14})

    assert response.status_code == 404


def test_admin_get_subscription_requires_super_admin():
    client, db, user = build_app_and_db()
    client.app.dependency_overrides[get_current_super_admin] = _deny_super_admin

    response = client.get(f"/billing/admin/subscriptions/{user.id}")

    assert response.status_code == 403


def test_admin_get_subscription_returns_target_users_subscription():
    client, db, user = build_app_and_db()
    db.add(Subscription(user_id=user.id, status=SubscriptionStatusEnum.CANCELED.value))
    db.commit()
    admin = User(name="Admin", email="admin@example.com")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    client.app.dependency_overrides[get_current_super_admin] = lambda: admin

    response = client.get(f"/billing/admin/subscriptions/{user.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELED"


def test_webhook_returns_500_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_WEBHOOK_TOKEN", None)
    client, db, _ = build_app_and_db()

    response = client.post(
        "/webhook/asaas",
        content=json.dumps({"event": "PAYMENT_CONFIRMED"}),
        headers={"asaas-access-token": "anything"},
    )

    assert response.status_code == 500
