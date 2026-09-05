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
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
    UserRole,
)
from app.models.schemas import ProfessionalPatientCreate
from app.services.patient_link_service import PatientLinkService
from app.services.professional_capacity_service import (
    DEFAULT_PROFESSIONAL_PATIENT_CAP,
    count_active_patients,
    require_patient_cap,
    resolve_patient_cap,
)
from app.services.professional_service import ProfessionalService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_professional(db, *, email="ana@example.com", free_until=None):
    professional_role = db.query(Role).filter(Role.name == RoleNameEnum.PROFESSIONAL.value).first()
    if not professional_role:
        professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
        db.add(professional_role)
        db.flush()
    professional = User(name="Dra. Ana", email=email)
    db.add(professional)
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=True, free_until=free_until)
    db.add(profile)
    db.commit()
    db.refresh(professional)
    db.refresh(profile)
    return professional, profile


def create_active_subscription(db, professional, *, plan_id="monthly"):
    db.add(Subscription(user_id=professional.id, status=SubscriptionStatusEnum.ACTIVE.value, plan_id=plan_id))
    db.commit()


def link_patient(db, profile, *, email):
    patient_role = db.query(Role).filter(Role.name == RoleNameEnum.PATIENT.value).first()
    if not patient_role:
        patient_role = Role(name=RoleNameEnum.PATIENT.value)
        db.add(patient_role)
        db.flush()
    patient = User(name="Paciente", email=email)
    db.add(patient)
    db.flush()
    db.add(UserRole(user_id=patient.id, role_id=patient_role.id))
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True, origin=MonitoringPlanOriginEnum.PROFESSIONAL.value)
    db.add(plan)
    db.flush()
    db.add(MonitoringProfessional(monitoring_plan_id=plan.id, professional_profile_id=profile.id, active=True))
    db.commit()
    return patient


def create_unlinked_patient(db, *, email):
    patient_role = db.query(Role).filter(Role.name == RoleNameEnum.PATIENT.value).first()
    if not patient_role:
        patient_role = Role(name=RoleNameEnum.PATIENT.value)
        db.add(patient_role)
        db.flush()
    patient = User(name="Paciente", email=email)
    db.add(patient)
    db.flush()
    db.add(UserRole(user_id=patient.id, role_id=patient_role.id))
    db.commit()
    db.refresh(patient)
    return patient


def patient_payload(**overrides):
    data = {
        "name": "Novo Paciente",
        "email": "novo@example.com",
        "plan_title": "Acompanhamento",
    }
    data.update(overrides)
    return ProfessionalPatientCreate(**data)


def test_count_active_patients_ignores_inactive_plans_and_links():
    db = build_session()
    _, profile = create_professional(db)
    link_patient(db, profile, email="ativo@example.com")
    inactive_plan_patient = link_patient(db, profile, email="planoinativo@example.com")
    db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == inactive_plan_patient.id).update({"active": False})
    inactive_link_patient = link_patient(db, profile, email="vinculoinativo@example.com")
    db.query(MonitoringProfessional).filter(MonitoringProfessional.professional_profile_id == profile.id, MonitoringProfessional.monitoring_plan_id.in_(
        db.query(MonitoringPlan.id).filter(MonitoringPlan.patient_id == inactive_link_patient.id)
    )).update({"active": False}, synchronize_session=False)
    db.commit()

    assert count_active_patients(db, profile.id) == 1


def test_count_active_patients_excludes_patients_with_own_subscription():
    db = build_session()
    _, profile = create_professional(db)
    link_patient(db, profile, email="autopagante@example.com")
    self_paying_patient = link_patient(db, profile, email="assinante@example.com")
    db.add(
        Subscription(
            user_id=self_paying_patient.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            plan_id="monthly",
        )
    )
    db.commit()

    assert count_active_patients(db, profile.id) == 1


def test_require_patient_cap_allows_beyond_limit_when_extra_patients_self_pay():
    db = build_session()
    professional, profile = create_professional(db, free_until=None)
    create_active_subscription(db, professional)
    # cap - 1 non-paying patients plus one self-paying patient: total linked
    # patients equals the cap, but the self-paying one shouldn't count, so
    # there's still room for one more.
    for index in range(DEFAULT_PROFESSIONAL_PATIENT_CAP - 1):
        link_patient(db, profile, email=f"paciente{index}@example.com")
    self_paying_patient = link_patient(db, profile, email="assinante-extra@example.com")
    db.add(
        Subscription(
            user_id=self_paying_patient.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            plan_id="monthly",
        )
    )
    db.commit()

    require_patient_cap(db, profile)  # no exception -- the self-paying patient doesn't count


def test_list_patients_flags_patients_with_own_subscription():
    db = build_session()
    professional, profile = create_professional(db)
    link_patient(db, profile, email="autopagante@example.com")
    self_paying_patient = link_patient(db, profile, email="assinante@example.com")
    db.add(
        Subscription(
            user_id=self_paying_patient.id,
            status=SubscriptionStatusEnum.ACTIVE.value,
            plan_id="monthly",
        )
    )
    db.commit()

    items = {item.patient_id: item for item in ProfessionalService(db).list_patients(professional)}

    assert items[self_paying_patient.id].has_own_subscription is True
    other = next(item for pid, item in items.items() if pid != self_paying_patient.id)
    assert other.has_own_subscription is False


def test_resolve_patient_cap_none_when_grandfathered():
    db = build_session()
    _, profile = create_professional(db, free_until=date(2099, 1, 1))

    assert resolve_patient_cap(db, profile) is None


def test_resolve_patient_cap_defaults_to_ten_without_plan_id():
    db = build_session()
    _, profile = create_professional(db, free_until=None)
    db.add(Subscription(user_id=profile.user_id, status=SubscriptionStatusEnum.TRIALING.value, trial_ends_at=datetime.now(timezone.utc) + timedelta(days=5)))
    db.commit()

    assert resolve_patient_cap(db, profile) == DEFAULT_PROFESSIONAL_PATIENT_CAP


def test_resolve_patient_cap_reads_tier_from_plan_id(monkeypatch):
    db = build_session()
    professional, profile = create_professional(db, free_until=None)
    create_active_subscription(db, professional, plan_id="tier25_monthly")
    monkeypatch.setattr(
        "app.core.config.settings.ASAAS_PROFESSIONAL_TIER25_MONTHLY_PRICE_CENTS", 7990
    )

    assert resolve_patient_cap(db, profile) == 25


def test_require_patient_cap_bypasses_admin():
    db = build_session()
    require_patient_cap(db, None)  # no exception


def test_require_patient_cap_blocks_at_limit():
    db = build_session()
    professional, profile = create_professional(db, free_until=None)
    create_active_subscription(db, professional)
    for index in range(DEFAULT_PROFESSIONAL_PATIENT_CAP):
        link_patient(db, profile, email=f"paciente{index}@example.com")

    with pytest.raises(HTTPException) as exc_info:
        require_patient_cap(db, profile)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PROFESSIONAL_PATIENT_CAP_REACHED"
    assert exc_info.value.detail["cap"] == DEFAULT_PROFESSIONAL_PATIENT_CAP


def test_require_patient_cap_allows_below_limit():
    db = build_session()
    professional, profile = create_professional(db, free_until=None)
    create_active_subscription(db, professional)
    link_patient(db, profile, email="unico@example.com")

    require_patient_cap(db, profile)  # no exception


def test_create_patient_blocked_at_cap():
    db = build_session()
    professional, profile = create_professional(db, free_until=None)
    create_active_subscription(db, professional)
    for index in range(DEFAULT_PROFESSIONAL_PATIENT_CAP):
        link_patient(db, profile, email=f"cheio{index}@example.com")

    with pytest.raises(HTTPException) as exc_info:
        ProfessionalService(db).create_patient(professional, patient_payload())

    assert exc_info.value.status_code == 409
    assert db.query(MonitoringPlan).count() == DEFAULT_PROFESSIONAL_PATIENT_CAP


def test_create_patient_allowed_when_grandfathered_even_over_ten():
    db = build_session()
    professional, profile = create_professional(db, free_until=date(2099, 1, 1))
    for index in range(DEFAULT_PROFESSIONAL_PATIENT_CAP + 2):
        link_patient(db, profile, email=f"legado{index}@example.com")

    result = ProfessionalService(db).create_patient(professional, patient_payload())

    assert result.patient.email == "novo@example.com"


def test_respond_accept_blocked_at_cap(monkeypatch):
    db = build_session()
    professional, profile = create_professional(db, free_until=None)
    create_active_subscription(db, professional)
    for index in range(DEFAULT_PROFESSIONAL_PATIENT_CAP):
        link_patient(db, profile, email=f"lotado{index}@example.com")

    patient = create_unlinked_patient(db, email="aceitando@example.com")

    monkeypatch.setattr("app.services.patient_link_service.send_email", lambda **kwargs: True)
    created = PatientLinkService(db).create_request(professional, patient.email)

    with pytest.raises(HTTPException) as exc_info:
        PatientLinkService(db).respond(patient, created["id"], True)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PROFESSIONAL_PATIENT_CAP_REACHED"


def test_respond_accept_blocked_when_professional_lost_billing_access(monkeypatch):
    db = build_session()
    professional, profile = create_professional(db, free_until=date(2099, 1, 1))
    patient = create_unlinked_patient(db, email="paciente@example.com")

    monkeypatch.setattr("app.services.patient_link_service.send_email", lambda **kwargs: True)
    created = PatientLinkService(db).create_request(professional, patient.email)

    # Grace period lapses between the request being sent and the patient accepting it.
    profile.free_until = date(2000, 1, 1)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        PatientLinkService(db).respond(patient, created["id"], True)

    assert exc_info.value.status_code == 402
    assert db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient.id, MonitoringPlan.active.is_(True)).count() == 0
