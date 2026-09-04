from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_admin, get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import (
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    Role,
    RoleNameEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
    UserRole,
)
from app.routes import anamnese_routes, monitoring_routes, self_monitoring_routes
from app.services import self_monitoring_service as self_monitoring_service_module
from app.services.payment_service import PaymentService
from app.services.self_monitoring_service import SelfMonitoringService


def _deny_admin():
    raise HTTPException(status_code=403, detail="Admin privileges required")


def build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()

    patient_role = Role(name=RoleNameEnum.PATIENT.value)
    db.add(patient_role)
    db.flush()
    self_service_patient = User(name="Paciente Autonomo", email="autonomo@example.com", phone="5511999990000")
    db.add(self_service_patient)
    db.flush()
    db.add(UserRole(user_id=self_service_patient.id, role_id=patient_role.id))
    db.commit()
    db.refresh(self_service_patient)

    app = FastAPI()
    app.include_router(self_monitoring_routes.router, prefix="/self-monitoring")
    app.include_router(anamnese_routes.router, prefix="/anamneses")
    app.include_router(monitoring_routes.router, prefix="/monitoring")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: self_service_patient
    app.dependency_overrides[get_current_admin] = _deny_admin
    return TestClient(app), db, self_service_patient


def test_self_service_patient_can_create_own_plan():
    client, db, patient = build_client()

    response = client.post("/self-monitoring/plan")

    assert response.status_code == 201
    body = response.json()
    assert body["patient_id"] == patient.id
    assert body["origin"] == "SELF_SERVICE"
    assert body["title"] == "Automonitoramento"

    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).one()
    assert plan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value


def test_self_service_plan_creation_is_idempotent():
    client, db, patient = build_client()

    first = client.post("/self-monitoring/plan").json()
    second = client.post("/self-monitoring/plan").json()

    assert first["id"] == second["id"]
    assert db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id).count() == 1


def test_self_service_patient_can_get_evolution_report_once_granted_access():
    client, db, patient = build_client()
    client.post("/self-monitoring/plan")
    subscription = PaymentService(db).get_or_create_subscription_record(patient)
    subscription.status = SubscriptionStatusEnum.ACTIVE.value
    db.commit()

    response = client.get("/self-monitoring/evolution-report")

    assert response.status_code == 200
    body = response.json()
    assert body["period_days"] == 30
    assert body["metrics"]["total_checkins"] == 0


def test_evolution_report_accepts_a_custom_period_up_to_one_year():
    client, db, patient = build_client()
    client.post("/self-monitoring/plan")
    subscription = PaymentService(db).get_or_create_subscription_record(patient)
    subscription.status = SubscriptionStatusEnum.ACTIVE.value
    db.commit()
    end_date = date.today()
    start_date = end_date - timedelta(days=364)

    response = client.get(
        "/self-monitoring/evolution-report",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["period_days"] == 365
    assert body["start_date"] == start_date.isoformat()
    assert body["end_date"] == end_date.isoformat()


def test_evolution_report_rejects_a_period_longer_than_one_year():
    client, db, patient = build_client()
    client.post("/self-monitoring/plan")
    subscription = PaymentService(db).get_or_create_subscription_record(patient)
    subscription.status = SubscriptionStatusEnum.ACTIVE.value
    db.commit()
    end_date = date.today()
    start_date = end_date - timedelta(days=400)

    response = client.get(
        "/self-monitoring/evolution-report",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "PERIOD_TOO_LONG"


def test_creating_plan_no_longer_starts_a_free_trial():
    client, db, patient = build_client()

    client.post("/self-monitoring/plan")

    # There is no automatic trial anymore -- access only ever comes from a
    # real payment or an admin-granted manual trial (see test_payment_routes.py),
    # so plan creation alone must not produce a Subscription row at all.
    assert db.query(Subscription).filter(Subscription.user_id == patient.id).first() is None


def test_evolution_report_blocked_after_manually_granted_trial_expires():
    client, db, patient = build_client()
    client.post("/self-monitoring/plan")
    subscription = PaymentService(db).grant_manual_trial(patient, days=1)
    subscription.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    response = client.get("/self-monitoring/evolution-report")

    assert response.status_code == 402


def test_evolution_report_blocked_without_any_subscription():
    client, db, patient = build_client()
    plan = MonitoringPlan(
        patient_id=patient.id,
        title="Automonitoramento",
        active=True,
        origin=MonitoringPlanOriginEnum.SELF_SERVICE.value,
    )
    db.add(plan)
    db.commit()

    response = client.get("/self-monitoring/evolution-report")

    assert response.status_code == 402


def test_evolution_report_allowed_when_subscription_active():
    client, db, patient = build_client()
    client.post("/self-monitoring/plan")
    subscription = PaymentService(db).get_or_create_subscription_record(patient)
    subscription.status = SubscriptionStatusEnum.ACTIVE.value
    db.commit()

    response = client.get("/self-monitoring/evolution-report")

    assert response.status_code == 200


def test_self_service_patient_cannot_create_anamnese_via_generic_route():
    client, _, patient = build_client()

    response = client.post("/anamneses/", json={"user_id": patient.id, "info": "auto-relato"})

    assert response.status_code == 403


def test_self_service_patient_cannot_use_generic_monitoring_plan_endpoint():
    client, _, patient = build_client()

    response = client.post(
        "/monitoring/plans",
        json={"title": "Plano manual", "patient_id": patient.id, "active": True},
    )

    assert response.status_code == 403


def test_create_or_reactivate_plan_reuses_existing_active_plan():
    _, db, patient = build_client()
    service = SelfMonitoringService(db)

    first = service.create_or_reactivate_plan(patient)
    second = service.create_or_reactivate_plan(patient)

    assert first.id == second.id
    assert db.query(MonitoringPlan).count() == 1


def test_create_plan_uses_brazil_calendar_day_not_server_utc_day(monkeypatch):
    # 01:30 UTC on the 27th is still 22:30 on the 26th in America/Sao_Paulo
    # (UTC-3) -- a plan created in this window on a UTC-clocked server must
    # not get "tomorrow" as its start_date, or _get_active_plan's
    # `start_date <= today` filter (computed in Brazil's timezone) rejects
    # it until the calendar day catches up.
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed_utc = datetime(2026, 8, 27, 1, 30, tzinfo=timezone.utc)
            return fixed_utc if tz is None else fixed_utc.astimezone(tz)

    monkeypatch.setattr(self_monitoring_service_module, "datetime", FixedDatetime)
    _, db, patient = build_client()
    service = SelfMonitoringService(db)

    plan = service.create_or_reactivate_plan(patient)

    assert plan.start_date.isoformat() == "2026-08-26"
