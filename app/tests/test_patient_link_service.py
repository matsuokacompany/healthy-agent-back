from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.models import (
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    MonitoringProfessional,
    PatientLinkRequest,
    PatientLinkRequestStatusEnum,
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
    UserRole,
)
from app.services.patient_link_service import PatientLinkService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_professional(db, *, email="ana@example.com", active=True, free_until=date(2099, 1, 1)):
    professional_role = db.query(Role).filter(Role.name == RoleNameEnum.PROFESSIONAL.value).first()
    if not professional_role:
        professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
        db.add(professional_role)
        db.flush()
    professional = User(name="Dra. Ana", email=email)
    db.add(professional)
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=active, specialty="Nutricionista", free_until=free_until)
    db.add(profile)
    db.commit()
    db.refresh(professional)
    db.refresh(profile)
    return professional, profile


def create_patient(db, *, email="paciente@example.com", name="Paciente"):
    patient_role = db.query(Role).filter(Role.name == RoleNameEnum.PATIENT.value).first()
    if not patient_role:
        patient_role = Role(name=RoleNameEnum.PATIENT.value)
        db.add(patient_role)
        db.flush()
    patient = User(name=name, email=email, phone=f"5511{abs(hash(email)) % 100000000:08d}")
    db.add(patient)
    db.flush()
    db.add(UserRole(user_id=patient.id, role_id=patient_role.id))
    db.commit()
    db.refresh(patient)
    return patient


def test_create_request_requires_active_professional_profile():
    db = build_session()
    non_professional = User(name="Someone", email="someone@example.com")
    db.add(non_professional)
    db.commit()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).create_request(non_professional, patient.email)

    assert exc.value.status_code == 403


def test_create_request_blocked_without_professional_billing_access():
    db = build_session()
    professional, _ = create_professional(db, free_until=None)
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).create_request(professional, patient.email)

    assert exc.value.status_code == 402


def test_create_request_requires_existing_patient_email():
    db = build_session()
    professional, _ = create_professional(db)

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).create_request(professional, "nobody@example.com")

    assert exc.value.status_code == 404


def test_create_request_rejects_non_patient_account():
    db = build_session()
    professional, _ = create_professional(db)
    other_professional, _ = create_professional(db, email="other@example.com")

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).create_request(professional, other_professional.email)

    assert exc.value.status_code == 409


def test_create_request_rejects_already_linked_patient():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_patient(db)
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.PROFESSIONAL.value)
    db.add(plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, active=True))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).create_request(professional, patient.email)

    assert exc.value.status_code == 409


def test_create_request_succeeds_and_lists_for_professional():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)

    created = PatientLinkService(db).create_request(professional, patient.email)

    assert created["status"] == "PENDING"
    assert created["patient_email"] == patient.email
    stored = db.query(PatientLinkRequest).one()
    expires_at = stored.expires_at.replace(tzinfo=timezone.utc) if stored.expires_at.tzinfo is None else stored.expires_at
    assert expires_at > datetime.now(timezone.utc)

    sent = PatientLinkService(db).list_sent_requests(professional)
    assert len(sent) == 1
    assert sent[0]["patient_name"] == patient.name


def test_create_request_notifies_patient_by_email(monkeypatch):
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    calls = []
    monkeypatch.setattr(
        "app.services.patient_link_service.send_email",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    PatientLinkService(db).create_request(professional, patient.email)

    assert len(calls) == 1
    assert calls[0]["to"] == patient.email
    assert professional.name in calls[0]["body"]


def test_create_request_rejects_duplicate_pending_request():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    PatientLinkService(db).create_request(professional, patient.email)

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).create_request(professional, patient.email)

    assert exc.value.status_code == 409


def test_list_incoming_requests_for_patient():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    PatientLinkService(db).create_request(professional, patient.email)

    incoming = PatientLinkService(db).list_incoming_requests(patient)

    assert len(incoming) == 1
    assert incoming[0]["professional_name"] == professional.name
    assert incoming[0]["professional_specialty"] == "Nutricionista"


def test_respond_reject_does_not_create_plan():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    created = PatientLinkService(db).create_request(professional, patient.email)

    result = PatientLinkService(db).respond(patient, created["id"], False)

    assert result["status"] == "REJECTED"
    assert db.query(MonitoringPlan).count() == 0


def test_respond_accept_creates_plan_and_link():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_patient(db)
    created = PatientLinkService(db).create_request(professional, patient.email)

    result = PatientLinkService(db).respond(patient, created["id"], True)

    assert result["status"] == "ACCEPTED"
    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id, MonitoringPlan.active.is_(True)).one()
    assert plan.origin == MonitoringPlanOriginEnum.PROFESSIONAL.value
    link = db.query(MonitoringProfessional).filter(MonitoringProfessional.monitoring_plan_id == plan.id).one()
    assert link.professional_profile_id == profile.id
    assert link.active is True


def test_respond_accept_deactivates_self_service_plan_but_keeps_subscription():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    self_service_plan = MonitoringPlan(patient_id=patient.id, title="Automonitoramento", active=True, origin=MonitoringPlanOriginEnum.SELF_SERVICE.value)
    db.add(self_service_plan)
    db.add(Subscription(user_id=patient.id, status=SubscriptionStatusEnum.TRIALING.value, trial_ends_at=datetime.now(timezone.utc) + timedelta(days=10)))
    db.commit()

    created = PatientLinkService(db).create_request(professional, patient.email)
    PatientLinkService(db).respond(patient, created["id"], True)

    db.refresh(self_service_plan)
    assert self_service_plan.active is False
    # The self-service subscription is left running — the platform never
    # cancels a patient's own paid subscription on their behalf.
    subscription = db.query(Subscription).filter(Subscription.user_id == patient.id).one()
    assert subscription.status == SubscriptionStatusEnum.TRIALING.value


def test_respond_accept_grants_professional_bonus_credit_when_patient_pays():
    db = build_session()
    professional, profile = create_professional(db)
    patient = create_patient(db)
    db.add(Subscription(user_id=patient.id, status=SubscriptionStatusEnum.ACTIVE.value))
    db.commit()

    created = PatientLinkService(db).create_request(professional, patient.email)
    PatientLinkService(db).respond(patient, created["id"], True)

    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id, MonitoringPlan.active.is_(True)).one()
    link = db.query(MonitoringProfessional).filter(MonitoringProfessional.monitoring_plan_id == plan.id).one()
    assert link.bonus_report_credits == 1


def test_respond_accept_grants_no_bonus_credit_without_paid_subscription():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)

    created = PatientLinkService(db).create_request(professional, patient.email)
    PatientLinkService(db).respond(patient, created["id"], True)

    plan = db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id, MonitoringPlan.active.is_(True)).one()
    link = db.query(MonitoringProfessional).filter(MonitoringProfessional.monitoring_plan_id == plan.id).one()
    assert link.bonus_report_credits == 0


def test_respond_accept_fails_when_already_linked_to_another_professional():
    db = build_session()
    professional, _ = create_professional(db)
    other_professional, other_profile = create_professional(db, email="other@example.com")
    patient = create_patient(db)
    created = PatientLinkService(db).create_request(professional, patient.email)

    # Simulate a race: patient got linked to someone else after the request was created.
    other_plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.PROFESSIONAL.value)
    db.add(other_plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=other_plan.id, professional_profile_id=other_profile.id, active=True))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).respond(patient, created["id"], True)

    assert exc.value.status_code == 409


def test_respond_rejects_already_resolved_request():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    created = PatientLinkService(db).create_request(professional, patient.email)
    PatientLinkService(db).respond(patient, created["id"], False)

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).respond(patient, created["id"], True)

    assert exc.value.status_code == 409


def test_respond_rejects_unknown_request_for_patient():
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).respond(patient, 999, True)

    assert exc.value.status_code == 404


def test_respond_marks_expired_request_and_returns_410():
    db = build_session()
    professional, _ = create_professional(db)
    patient = create_patient(db)
    created = PatientLinkService(db).create_request(professional, patient.email)
    stored = db.query(PatientLinkRequest).filter(PatientLinkRequest.id == created["id"]).one()
    stored.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        PatientLinkService(db).respond(patient, created["id"], True)

    assert exc.value.status_code == 410
    db.refresh(stored)
    assert stored.status == PatientLinkRequestStatusEnum.EXPIRED.value
