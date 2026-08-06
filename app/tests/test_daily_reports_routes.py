from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.dependencies import get_db
from app.db.base_class import Base
from app.models.models import CheckTypeEnum, DailyReport, MonitoringPlan, User
from app.routes import daily_reports_routes


def build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()

    current_user = User(name="Paciente", email="patient@example.com", phone="5511999999999")
    other_user = User(name="Outro", email="other@example.com", phone="5511888888888")
    db.add_all([current_user, other_user])
    db.commit()
    db.refresh(current_user)
    db.refresh(other_user)

    app = FastAPI()
    app.include_router(daily_reports_routes.router, prefix="/daily-reports")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app), db, current_user, other_user


def create_report(db, user, *, check_type=CheckTypeEnum.MORNING):
    plan = MonitoringPlan(
        patient_id=user.id,
        title=f"Plano {user.id}",
        active=True,
        start_date=date.today(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    now = datetime.now(timezone.utc)
    report = DailyReport(
        user_id=user.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type=check_type,
        prompt_sent_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_patient_can_update_own_response():
    client, db, current_user, _ = build_client()
    report = create_report(db, current_user)

    response = client.patch(
        f"/daily-reports/{report.id}",
        json={"had_symptoms": True, "symptom_description": "  Dor de cabeça  "},
    )

    assert response.status_code == 200
    assert response.json()["had_symptoms"] is True
    assert response.json()["symptom_description"] == "Dor de cabeça"


def test_patient_cannot_update_another_patients_response():
    client, db, _, other_user = build_client()
    report = create_report(db, other_user)

    response = client.patch(
        f"/daily-reports/{report.id}",
        json={"had_symptoms": False},
    )

    assert response.status_code == 404


def test_patient_cannot_delete_another_patients_response():
    client, db, _, other_user = build_client()
    report = create_report(db, other_user)

    response = client.delete(f"/daily-reports/{report.id}/response")

    assert response.status_code == 404


def test_update_nonexistent_report_returns_not_found():
    client, _, _, _ = build_client()

    response = client.patch(
        "/daily-reports/999999",
        json={"had_symptoms": False},
    )

    assert response.status_code == 404


def test_update_rejects_description_longer_than_280_characters():
    client, db, current_user, _ = build_client()
    report = create_report(db, current_user)

    response = client.patch(
        f"/daily-reports/{report.id}",
        json={"had_symptoms": True, "symptom_description": "x" * 281},
    )

    assert response.status_code == 422


def test_update_requires_description_when_symptoms_are_reported():
    client, db, current_user, _ = build_client()
    report = create_report(db, current_user)

    response = client.patch(
        f"/daily-reports/{report.id}",
        json={"had_symptoms": True, "symptom_description": "   "},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "A symptom description is required when symptoms are reported"
