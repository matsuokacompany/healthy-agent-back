from io import BytesIO
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import ClinicalAttachmentSourceEnum, DailyReport, MonitoringPlan, User
from app.services.clinical_attachment_service import ClinicalAttachmentService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def jpeg_bytes(size=(2400, 1800)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color="white").save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def enable_images(monkeypatch):
    monkeypatch.setattr(settings, "CLINICAL_IMAGES_ENABLED", True)
    monkeypatch.setattr(settings, "PORTAL_CLINICAL_IMAGES_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_CLINICAL_IMAGES_ENABLED", True)
    monkeypatch.setattr(settings, "CLINICAL_IMAGE_MAX_STORED_PER_PATIENT", 30)
    monkeypatch.setattr(ClinicalAttachmentService, "_upload", lambda *args: None)


def create_patient(db):
    patient = User(name="Paciente", email="patient@example.com", supabase_user_id=uuid.uuid4())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def test_patient_upload_is_normalized_and_stored_privately():
    db = build_session()
    patient = create_patient(db)

    attachment = ClinicalAttachmentService(db).create(
        actor=patient,
        patient_id=patient.id,
        content=jpeg_bytes(),
        declared_content_type="image/jpeg",
        description=" Região inferior ",
    )

    assert attachment.source == ClinicalAttachmentSourceEnum.PATIENT_PORTAL.value
    assert attachment.content_type == "image/jpeg"
    assert attachment.description == "Região inferior"
    assert attachment.object_key.startswith(f"patients/{patient.supabase_user_id}/attachments/")


def test_whatsapp_allows_only_one_active_image_per_report():
    db = build_session()
    patient = create_patient(db)
    plan = MonitoringPlan(patient_id=patient.id, title="Plano", active=True)
    db.add(plan)
    db.flush()
    report = DailyReport(
        user_id=patient.id,
        monitoring_plan_id=plan.id,
        report_date=date.today(),
        check_type="MORNING",
        prompt_sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(report)
    db.commit()

    service = ClinicalAttachmentService(db)
    service.create(
        actor=patient,
        patient_id=patient.id,
        content=jpeg_bytes((100, 100)),
        declared_content_type="image/jpeg",
        daily_report_id=report.id,
        source=ClinicalAttachmentSourceEnum.WHATSAPP,
        whatsapp_message_id="wamid-1",
        whatsapp_media_id="media-1",
    )

    with pytest.raises(HTTPException) as exc:
        service.create(
            actor=patient,
            patient_id=patient.id,
            content=jpeg_bytes((100, 100)),
            declared_content_type="image/jpeg",
            daily_report_id=report.id,
            source=ClinicalAttachmentSourceEnum.WHATSAPP,
            whatsapp_message_id="wamid-2",
            whatsapp_media_id="media-2",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "WHATSAPP_IMAGE_LIMIT_REACHED"


def test_invalid_image_is_rejected():
    db = build_session()
    patient = create_patient(db)

    with pytest.raises(HTTPException) as exc:
        ClinicalAttachmentService(db).create(
            actor=patient,
            patient_id=patient.id,
            content=b"not-an-image",
            declared_content_type="image/jpeg",
        )

    assert exc.value.status_code == 415
    assert exc.value.detail == "INVALID_IMAGE"
