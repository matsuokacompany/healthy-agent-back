from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import Role, RoleNameEnum, User, UserRole
from app.routes import admin_routes


def build_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def build_app(db, current_user):
    app = FastAPI()
    app.include_router(admin_routes.router, prefix="/admin")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def create_super_admin(db):
    role = Role(name=RoleNameEnum.SUPER_ADMIN.value)
    db.add(role)
    db.flush()
    user = User(name="Admin", email="admin@example.com")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def create_patient(db):
    role = Role(name=RoleNameEnum.PATIENT.value)
    db.add(role)
    db.flush()
    user = User(name="Paciente", email="paciente@example.com")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def test_admin_endpoints_require_super_admin():
    db = build_db()
    patient = create_patient(db)
    client = build_app(db, patient)

    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/costs").status_code == 403
    assert client.get("/admin/whatsapp/stats").status_code == 403


def test_super_admin_can_list_users_and_read_costs_and_whatsapp_stats():
    db = build_db()
    admin = create_super_admin(db)
    client = build_app(db, admin)

    users_response = client.get("/admin/users")
    assert users_response.status_code == 200
    assert users_response.json()[0]["email"] == "admin@example.com"

    costs_response = client.get("/admin/costs")
    assert costs_response.status_code == 200
    assert costs_response.json()["ai_report_count"] == 0

    whatsapp_response = client.get("/admin/whatsapp/stats?days=7")
    assert whatsapp_response.status_code == 200
    assert whatsapp_response.json()["period_days"] == 7

    billing_response = client.get("/admin/billing/summary")
    assert billing_response.status_code == 200
    assert billing_response.json()["mrr_cents"] == 0


def test_billing_summary_requires_super_admin():
    db = build_db()
    patient = create_patient(db)
    client = build_app(db, patient)

    assert client.get("/admin/billing/summary").status_code == 403


def test_super_admin_can_create_list_and_delete_cost_entries():
    db = build_db()
    admin = create_super_admin(db)
    client = build_app(db, admin)

    create_response = client.post(
        "/admin/costs/entries",
        json={"description": "Contrato de suporte", "category": "Operações", "amount_cents": 15000, "incurred_on": "2026-08-01"},
    )
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]
    assert create_response.json()["created_by_user_id"] == admin.id

    list_response = client.get("/admin/costs/entries")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    summary_response = client.get("/admin/costs?start_date=2026-08-01&end_date=2026-08-31")
    assert summary_response.json()["manual_cost_total_cents"] == 15000
    assert len(summary_response.json()["manual_cost_entries"]) == 1

    delete_response = client.delete(f"/admin/costs/entries/{entry_id}")
    assert delete_response.status_code == 204
    assert client.get("/admin/costs/entries").json() == []


def test_non_admin_cannot_manage_cost_entries():
    db = build_db()
    patient = create_patient(db)
    client = build_app(db, patient)

    assert (
        client.post(
            "/admin/costs/entries",
            json={"description": "x", "amount_cents": 100, "incurred_on": "2026-08-01"},
        ).status_code
        == 403
    )
    assert client.get("/admin/costs/entries").status_code == 403
    assert client.delete("/admin/costs/entries/1").status_code == 403
