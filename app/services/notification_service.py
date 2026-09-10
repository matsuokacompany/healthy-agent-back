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


def notify_patient_inactive(db: Session, *, patient: User, days: int) -> None:
    """Called by the scheduler when a patient's last `days` daily check-ins
    (the most recent ones the scheduler actually sent, whether or not
    answered) were all left incomplete -- fired only at day=3 (first notice)
    and day=7 (one escalation), never on every day the streak continues, so
    reading this notification never becomes routine to ignore."""
    professional_user_ids = assigned_professional_user_ids(db, patient.id)
    if professional_user_ids:
        message = f"{patient.name} está há {days} dias sem completar o check-in."
        for professional_user_id in professional_user_ids:
            create_notification(db, user_id=professional_user_id, kind=NotificationKindEnum.PATIENT_INACTIVE, message=message)
        return
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.PATIENT_INACTIVE,
        message=f"Você não fez seu check-in nos últimos {days} dias. Quer continuar seu acompanhamento?",
    )


def notify_medication_adherence_none(db: Session, *, patient: User) -> None:
    """Called by the scheduler the first time a patient's two most recent
    *completed* check-ins both report medication_adherence_level=NONE --
    fired once when the streak reaches exactly two, not on every completed
    check-in afterwards that keeps it going."""
    professional_user_ids = assigned_professional_user_ids(db, patient.id)
    if professional_user_ids:
        message = f"{patient.name} não registrou ter tomado nenhum remédio/suplemento nos últimos 2 dias."
        for professional_user_id in professional_user_ids:
            create_notification(db, user_id=professional_user_id, kind=NotificationKindEnum.MEDICATION_ADHERENCE_ALERT, message=message)
        return
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.MEDICATION_ADHERENCE_ALERT,
        message="Você não registrou ter tomado seus remédios/suplementos nos últimos 2 dias. Foi intencional?",
    )


def notify_symptom_pattern(db: Session, *, patient: User, term_label: str, occurrences: int) -> None:
    """Called by the scheduler when the same normalized symptom term shows
    up `occurrences` times (>=3) in the patient's last 7 days of check-ins.
    Deduplicated per-patient (not per-term) with a 7-day cooldown by the
    caller, so a persistent symptom doesn't re-notify every day."""
    professional_user_ids = assigned_professional_user_ids(db, patient.id)
    if professional_user_ids:
        message = f"{patient.name} relatou \"{term_label}\" {occurrences} vezes nos últimos 7 dias."
        for professional_user_id in professional_user_ids:
            create_notification(db, user_id=professional_user_id, kind=NotificationKindEnum.SYMPTOM_PATTERN_ALERT, message=message)
        return
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.SYMPTOM_PATTERN_ALERT,
        message=f"Você relatou \"{term_label}\" {occurrences} vezes essa semana. Pode ser hora de conversar com um profissional de saúde.",
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
