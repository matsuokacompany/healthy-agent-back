"""Shared helpers for writing in-app Notification rows for product events
(as opposed to the billing/dunning ones in dunning_service.py and
payment_service.py). Centralizes the "which professionals are currently
assigned to this patient" query, since several event kinds need it.
"""

from sqlalchemy.orm import Session

from app.models.models import (
    DailyReport,
    MonitoringPlan,
    MonitoringProfessional,
    Notification,
    NotificationKindEnum,
    ProfessionalProfile,
    Supplement,
    User,
)


def create_notification(db: Session, *, user_id: int, kind: NotificationKindEnum, message: str) -> None:
    db.add(Notification(user_id=user_id, kind=kind.value, message=message))


def assigned_professional_user_ids(
    db: Session, patient_id: int, *, exclude_user_id: int | None = None
) -> list[int]:
    """User ids of professionals with an active link to this patient's active
    monitoring plan(s)."""
    query = (
        db.query(ProfessionalProfile.user_id)
        .join(MonitoringProfessional, MonitoringProfessional.professional_profile_id == ProfessionalProfile.id)
        .join(MonitoringPlan, MonitoringPlan.id == MonitoringProfessional.monitoring_plan_id)
        .filter(
            MonitoringPlan.patient_id == patient_id,
            MonitoringPlan.active.is_(True),
            MonitoringProfessional.active.is_(True),
        )
        .distinct()
    )
    user_ids = [row[0] for row in query.all()]
    if exclude_user_id is not None:
        user_ids = [user_id for user_id in user_ids if user_id != exclude_user_id]
    return user_ids


def notify_symptom_reported(db: Session, *, patient: User, report: DailyReport) -> None:
    """Called once a check-in lands as COMPLETED with had_symptoms=True,
    from whichever channel produced it (WhatsApp bot or the patient/professional
    editing the report through the API)."""
    professional_user_ids = assigned_professional_user_ids(db, patient.id)
    if not professional_user_ids:
        return
    message = f"{patient.name} relatou sintomas no check-in de hoje."
    for professional_user_id in professional_user_ids:
        create_notification(db, user_id=professional_user_id, kind=NotificationKindEnum.SYMPTOM_REPORTED, message=message)


def notify_ai_report_ready(db: Session, *, patient: User, generated_by_user_id: int) -> None:
    """Called only when a genuinely new AiReportCache row is written (not on
    a cache hit), so co-assigned professionals other than whoever requested
    it learn a fresh report exists without having to check themselves."""
    professional_user_ids = assigned_professional_user_ids(db, patient.id, exclude_user_id=generated_by_user_id)
    if not professional_user_ids:
        return
    message = f"Novo relatório de IA disponível para {patient.name}."
    for professional_user_id in professional_user_ids:
        create_notification(db, user_id=professional_user_id, kind=NotificationKindEnum.AI_REPORT_READY, message=message)


def notify_patient_assigned(db: Session, *, professional_user_id: int, patient: User) -> None:
    create_notification(
        db,
        user_id=professional_user_id,
        kind=NotificationKindEnum.PATIENT_ASSIGNED,
        message=f"{patient.name} foi vinculado(a) ao seu acompanhamento.",
    )


def notify_checkin_pending(db: Session, *, patient_user_id: int) -> None:
    create_notification(
        db,
        user_id=patient_user_id,
        kind=NotificationKindEnum.CHECKIN_PENDING,
        message="Seu check-in de hoje ainda está pendente. Responda no WhatsApp antes que expire.",
    )


def notify_supplement_course_ended(db: Session, *, patient: User, supplement: Supplement) -> None:
    """Called once, by the daily scheduler job, the first time a
    duration-bound supplement's course has elapsed -- the WhatsApp
    medication question already stopped naming it (see
    SupplementService.is_active), so this is what actually tells the
    patient (and any assigned professionals) it's done."""
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.SUPPLEMENT_COURSE_ENDED,
        message=f"O período de uso de {supplement.name} chegou ao fim.",
    )
    for professional_user_id in assigned_professional_user_ids(db, patient.id):
        create_notification(
            db,
            user_id=professional_user_id,
            kind=NotificationKindEnum.SUPPLEMENT_COURSE_ENDED,
            message=f"O período de uso de {supplement.name} chegou ao fim para {patient.name}.",
        )
