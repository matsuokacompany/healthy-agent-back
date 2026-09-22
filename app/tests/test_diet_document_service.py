import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import DietDocument, User
from app.services.diet_document_service import DietDocumentService
from app.services.supabase_storage import SupabaseStorageClient


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_patient(db):
    patient = User(name="Paciente", email="patient@example.com", supabase_user_id=uuid.uuid4())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@pytest.fixture(autouse=True)
def enable_diet_documents(monkeypatch):
    monkeypatch.setattr(settings, "DIET_DOCUMENTS_ENABLED", True)
    monkeypatch.setattr(SupabaseStorageClient, "upload", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(SupabaseStorageClient, "delete", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(SupabaseStorageClient, "sign_url", lambda self, *args, **kwargs: "https://signed.example/plan.pdf")


PDF_BYTES = b"%PDF-1.4\n%mock\n%%EOF"


def test_upload_creates_a_document_for_a_patient_with_none():
    db = build_session()
    patient = create_patient(db)

    document = DietDocumentService(db).upload(
        actor=patient,
        patient_id=patient.id,
        content=PDF_BYTES,
        declared_content_type="application/pdf",
        original_filename="minha dieta.pdf",
    )

    assert document.patient_id == patient.id
    assert document.original_filename == "minha dieta.pdf"
    assert document.byte_size == len(PDF_BYTES)
    assert db.query(DietDocument).filter(DietDocument.patient_id == patient.id).count() == 1


def test_uploading_again_replaces_the_previous_document_in_place():
    db = build_session()
    patient = create_patient(db)
    service = DietDocumentService(db)
    first = service.upload(
        actor=patient,
        patient_id=patient.id,
        content=PDF_BYTES,
        declared_content_type="application/pdf",
        original_filename="dieta-v1.pdf",
    )

    second = service.upload(
        actor=patient,
        patient_id=patient.id,
        content=PDF_BYTES + b"more",
        declared_content_type="application/pdf",
        original_filename="dieta-v2.pdf",
    )

    assert second.id == first.id
    assert second.original_filename == "dieta-v2.pdf"
    assert db.query(DietDocument).filter(DietDocument.patient_id == patient.id).count() == 1


def test_upload_rejects_non_pdf_content_type():
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc_info:
        DietDocumentService(db).upload(
            actor=patient,
            patient_id=patient.id,
            content=PDF_BYTES,
            declared_content_type="image/jpeg",
            original_filename="dieta.jpg",
        )

    assert exc_info.value.status_code == 415


def test_upload_rejects_content_that_does_not_look_like_a_pdf():
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc_info:
        DietDocumentService(db).upload(
            actor=patient,
            patient_id=patient.id,
            content=b"not a real pdf",
            declared_content_type="application/pdf",
            original_filename="dieta.pdf",
        )

    assert exc_info.value.status_code == 415


def test_upload_rejects_oversized_document(monkeypatch):
    monkeypatch.setattr(settings, "DIET_DOCUMENT_MAX_UPLOAD_BYTES", 1)
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc_info:
        DietDocumentService(db).upload(
            actor=patient,
            patient_id=patient.id,
            content=PDF_BYTES,
            declared_content_type="application/pdf",
            original_filename="dieta.pdf",
        )

    assert exc_info.value.status_code == 413


def test_delete_removes_the_document():
    db = build_session()
    patient = create_patient(db)
    service = DietDocumentService(db)
    service.upload(
        actor=patient,
        patient_id=patient.id,
        content=PDF_BYTES,
        declared_content_type="application/pdf",
        original_filename="dieta.pdf",
    )

    service.delete(patient, patient.id)

    assert db.query(DietDocument).filter(DietDocument.patient_id == patient.id).count() == 0


def test_delete_404s_when_no_document_exists():
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc_info:
        DietDocumentService(db).delete(patient, patient.id)

    assert exc_info.value.status_code == 404


def test_upload_disabled_by_flag(monkeypatch):
    monkeypatch.setattr(settings, "DIET_DOCUMENTS_ENABLED", False)
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc_info:
        DietDocumentService(db).upload(
            actor=patient,
            patient_id=patient.id,
            content=PDF_BYTES,
            declared_content_type="application/pdf",
            original_filename="dieta.pdf",
        )

    assert exc_info.value.status_code == 503
