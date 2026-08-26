from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import (
    ProfessionalProfile,
    Role,
    RoleNameEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
    UserRole,
)
from app.models.schemas import ProfessionalPatientCreate
from app.services.payment_service import PaymentService, professional_has_access
from app.services.professional_service import ProfessionalService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_professional(db, *, free_until=None):
    professional_role = Role(name=RoleNameEnum.PROFESSIONAL.value)
    professional = User(name="Dr. Bruno", email="bruno@example.com", cpf="12345678900")
    db.add_all([professional_role, professional])
    db.flush()
    db.add(UserRole(user_id=professional.id, role_id=professional_role.id))
    profile = ProfessionalProfile(user_id=professional.id, active=True, free_until=free_until)
    db.add(profile)
    db.commit()
    db.refresh(professional)
    db.refresh(profile)
    return professional, profile


def patient_payload(**overrides):
    data = {
        "name": "Paciente Teste",
        "email": "paciente-teste@example.com",
        "phone": "+55 (11) 98888-0000",
        "plan_title": "Acompanhamento",
        "plan_start_date": date(2026, 8, 13),
    }
    data.update(overrides)
    return ProfessionalPatientCreate(**data)


# --- professional_has_access (pure logic) ---


def test_professional_has_access_true_while_within_free_until():
    profile = ProfessionalProfile(user_id=1, free_until=date.today() + timedelta(days=1))
    assert professional_has_access(profile, subscription=None) is True


def test_professional_has_access_false_after_free_until_with_no_subscription():
    profile = ProfessionalProfile(user_id=1, free_until=date.today() - timedelta(days=1))
    assert professional_has_access(profile, subscription=None) is False


def test_professional_has_access_true_with_active_subscription_no_grace():
    profile = ProfessionalProfile(user_id=1, free_until=None)
    subscription = Subscription(user_id=1, status=SubscriptionStatusEnum.ACTIVE.value)
    assert professional_has_access(profile, subscription) is True


def test_professional_has_access_false_with_no_grace_and_no_subscription():
    profile = ProfessionalProfile(user_id=1, free_until=None)
    assert professional_has_access(profile, subscription=None) is False


# --- start_checkout catalog selection ---


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsaasClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        if url.endswith("/customers"):
            return _FakeResponse(200, {"id": "cus_prof"})
        if url.endswith("/subscriptions"):
            self.subscription_payload = json
            return _FakeResponse(200, {"id": "sub_prof", "invoiceUrl": "https://asaas.test/i/prof"})
        raise AssertionError(f"Unexpected POST {url}")


def test_start_checkout_uses_professional_catalog_for_professional_role(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", None)
    monkeypatch.setattr(settings, "ASAAS_PROFESSIONAL_MONTHLY_PRICE_CENTS", 3990)
    db = build_session()
    professional, _ = create_professional(db)
    fake_client = _FakeAsaasClient()
    monkeypatch.setattr("app.services.payment_service.httpx.Client", lambda timeout=10.0: fake_client)

    result = PaymentService(db).start_checkout(professional, "monthly")

    assert result["checkout_url"] == "https://asaas.test/i/prof"
    assert fake_client.subscription_payload["value"] == 39.90


def test_start_checkout_rejects_professional_plan_id_for_patient(monkeypatch):
    monkeypatch.setattr(settings, "ASAAS_SELF_MONITORING_PRICE_CENTS", None)
    monkeypatch.setattr(settings, "ASAAS_PROFESSIONAL_MONTHLY_PRICE_CENTS", 3990)
    db = build_session()
    patient = User(name="Paciente", email="p@example.com", cpf="00000000000")
    db.add(patient)
    db.commit()
    db.refresh(patient)

    with pytest.raises(HTTPException) as exc:
        PaymentService(db).start_checkout(patient, "monthly")
    assert exc.value.status_code == 400


# --- ProfessionalService gating ---


def test_create_patient_blocked_without_billing_access():
    db = build_session()
    professional, _ = create_professional(db, free_until=None)

    with pytest.raises(HTTPException) as exc:
        ProfessionalService(db).create_patient(professional, patient_payload())
    assert exc.value.status_code == 402


def test_create_patient_allowed_within_grace_period(monkeypatch):
    from app.services import professional_service as professional_service_module

    monkeypatch.setattr(professional_service_module, "invite_supabase_user", lambda email, name=None: None)
    db = build_session()
    professional, _ = create_professional(db, free_until=date.today() + timedelta(days=1))

    result = ProfessionalService(db).create_patient(professional, patient_payload())
    assert result.patient.email == "paciente-teste@example.com"


def test_create_patient_allowed_with_active_subscription(monkeypatch):
    from app.services import professional_service as professional_service_module

    monkeypatch.setattr(professional_service_module, "invite_supabase_user", lambda email, name=None: None)
    db = build_session()
    professional, _ = create_professional(db, free_until=None)
    db.add(Subscription(user_id=professional.id, status=SubscriptionStatusEnum.ACTIVE.value))
    db.commit()

    result = ProfessionalService(db).create_patient(professional, patient_payload())
    assert result.patient.email == "paciente-teste@example.com"
