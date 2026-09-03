import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import Role, RoleNameEnum, User, UserRole
from app.services.support_service import SupportService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_patient(db, *, email="paciente@example.com"):
    role = Role(name=RoleNameEnum.PATIENT.value)
    db.add(role)
    db.flush()
    user = User(name="Maria Paciente", email=email)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def test_send_contact_message_emails_the_support_inbox(monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_CONTACT_EMAIL", "contato@julha.com.br")
    db = build_session()
    patient = create_patient(db)
    calls = []
    monkeypatch.setattr(
        "app.services.support_service.send_email",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    SupportService().send_contact_message(patient, subject="Problema técnico", message="A tela trava ao salvar.")

    assert len(calls) == 1
    call = calls[0]
    assert call["to"] == "contato@julha.com.br"
    assert call["subject"] == "[Suporte Julha] Problema técnico"
    assert patient.name in call["body"]
    assert patient.email in call["body"]
    assert "A tela trava ao salvar." in call["body"]
    assert call["attachment"] is None


def test_send_contact_message_includes_attachment(monkeypatch):
    db = build_session()
    patient = create_patient(db)
    calls = []
    monkeypatch.setattr(
        "app.services.support_service.send_email",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    SupportService().send_contact_message(
        patient,
        subject="Dúvida",
        message="Segue print.",
        attachment_content=b"fake-bytes",
        attachment_content_type="image/png",
        attachment_filename="print.png",
    )

    assert calls[0]["attachment"] == (b"fake-bytes", "print.png", "image/png")


def test_send_contact_message_rejects_unsupported_attachment_type():
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        SupportService().send_contact_message(
            patient,
            subject="Dúvida",
            message="Segue arquivo.",
            attachment_content=b"fake-bytes",
            attachment_content_type="application/pdf",
            attachment_filename="documento.pdf",
        )

    assert exc.value.status_code == 415


def test_send_contact_message_rejects_oversized_attachment(monkeypatch):
    monkeypatch.setattr(settings, "CLINICAL_IMAGE_MAX_UPLOAD_BYTES", 10)
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        SupportService().send_contact_message(
            patient,
            subject="Dúvida",
            message="Segue print.",
            attachment_content=b"x" * 11,
            attachment_content_type="image/png",
            attachment_filename="print.png",
        )

    assert exc.value.status_code == 413


def test_send_contact_message_raises_when_delivery_fails(monkeypatch):
    db = build_session()
    patient = create_patient(db)
    monkeypatch.setattr("app.services.support_service.send_email", lambda **kwargs: False)

    with pytest.raises(HTTPException) as exc:
        SupportService().send_contact_message(patient, subject="Problema técnico", message="Não consigo entrar.")

    assert exc.value.status_code == 502
