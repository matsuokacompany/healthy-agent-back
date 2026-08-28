from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import Notification, User
from app.routes import notification_routes


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
    app.include_router(notification_routes.router, prefix="/notifications")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user

    return TestClient(app), db, user


def test_list_notifications_returns_own_items_and_unread_count():
    client, db, user = build_app_and_db()
    db.add_all([
        Notification(user_id=user.id, kind="PAYMENT_OVERDUE", message="a"),
        Notification(user_id=user.id, kind="TRIAL_ENDING", message="b"),
    ])
    db.commit()

    response = client.get("/notifications")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["unread_count"] == 2


def test_list_notifications_excludes_other_users():
    client, db, user = build_app_and_db()
    other = User(name="Outro", email="outro@example.com", phone="5511999990001", cpf="98765432100")
    db.add(other)
    db.commit()
    db.refresh(other)
    db.add(Notification(user_id=other.id, kind="PAYMENT_OVERDUE", message="not yours"))
    db.commit()

    response = client.get("/notifications")

    assert response.json()["items"] == []


def test_mark_notification_read():
    client, db, user = build_app_and_db()
    notification = Notification(user_id=user.id, kind="PAYMENT_OVERDUE", message="a")
    db.add(notification)
    db.commit()
    db.refresh(notification)

    response = client.post(f"/notifications/{notification.id}/read")

    assert response.status_code == 200
    assert response.json()["read_at"] is not None


def test_mark_notification_read_404_for_other_users_notification():
    client, db, user = build_app_and_db()
    other = User(name="Outro", email="outro@example.com", phone="5511999990001", cpf="98765432100")
    db.add(other)
    db.commit()
    db.refresh(other)
    notification = Notification(user_id=other.id, kind="PAYMENT_OVERDUE", message="not yours")
    db.add(notification)
    db.commit()
    db.refresh(notification)

    response = client.post(f"/notifications/{notification.id}/read")

    assert response.status_code == 404


def test_mark_all_read():
    client, db, user = build_app_and_db()
    db.add_all([
        Notification(user_id=user.id, kind="PAYMENT_OVERDUE", message="a"),
        Notification(user_id=user.id, kind="TRIAL_ENDING", message="b"),
    ])
    db.commit()

    response = client.post("/notifications/read-all")

    assert response.status_code == 200
    assert response.json()["unread_count"] == 0
