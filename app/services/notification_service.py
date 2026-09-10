"""Shared helpers for writing in-app Notification rows for product events
(as opposed to the billing/dunning ones in dunning_service.py and
payment_service.py). Centralizes the "which professionals are currently
assigned to this patient" query, since several event kinds need it.
"""

import logging

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
from app.services.red_flag_symptoms import (
    RED_FLAG_CONTEXTUAL_SAFETY_MESSAGE_PT_BR,
    RED_FLAG_ORANGE_SAFETY_MESSAGE_PT_BR,
    RED_FLAG_SAFETY_MESSAGE_PT_BR,
)

logger = logging.getLogger(__name__)


def create_notification(db: Session, *, user_id: int, kind: NotificationKindEnum, message: str) -> None:
    db.add(Notification(user_id=user_id, kind=kind.value, message=message))


def send_push_notification(user: User, *, title: str, body: str) -> None:
    """The single point that will actually deliver a phone push, once a
    mobile app exists to register `User.push_token` and a provider
    (FCM/APNs/Expo) is wired up here -- today that's not the case, so this
    is a deliberate no-op regardless of `push_token`. Call sites (see
    notify_red_flag_symptom/notify_red_flag_symptom_contextual below)
    already call it with everything a real push would need, so wiring up a
    provider later only means filling in this one function's body."""
    if not user.push_token:
        return
    logger.info("Push notification would be sent (no provider configured yet) | user_id=%s title=%s", user.id, title)


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


def notify_red_flag_symptom(db: Session, *, patient: User, category_label: str) -> None:
    """Called by DailyReportService right when a check-in's free-text
    symptom description matches one of the reviewed RED_FLAG_ABSOLUTE
    categories (see red_flag_symptoms.py). Unlike the other notify_*
    helpers in this module, this always notifies the patient directly --
    only they can act on it in the moment, whether or not a professional
    is assigned -- and additionally notifies any assigned professional(s),
    since either side might see it first."""
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.RED_FLAG_SYMPTOM,
        message=RED_FLAG_SAFETY_MESSAGE_PT_BR,
    )
    send_push_notification(patient, title="Sinal de alerta identificado", body=RED_FLAG_SAFETY_MESSAGE_PT_BR)
    for professional_user_id in assigned_professional_user_ids(db, patient.id):
        create_notification(
            db,
            user_id=professional_user_id,
            kind=NotificationKindEnum.RED_FLAG_SYMPTOM,
            message=f"{patient.name} relatou um sinal de alerta ({category_label}) no check-in de hoje. Recomendamos contato o quanto antes.",
        )


def notify_red_flag_symptom_contextual(
    db: Session, *, patient: User, category_label: str, risk_factor_label: str
) -> None:
    """Called by DailyReportService when a check-in's free-text symptom
    description matches a RED_FLAG_CONTEXTUAL category (see
    red_flag_symptoms.py) AND the patient's anamnese has the specific risk
    factor that elevates it (RedFlagDetectionService.detect_for_patient
    already did that cross-reference) -- an otherwise-routine symptom
    escalated only because of that history. Same dual-notify shape as
    notify_red_flag_symptom: always notifies the patient directly (the
    generic contextual safety message, already also delivered inline in
    the WhatsApp reply -- see BotService._translate), plus any assigned
    professional(s), named with both the symptom and the risk factor."""
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.RED_FLAG_SYMPTOM,
        message=RED_FLAG_CONTEXTUAL_SAFETY_MESSAGE_PT_BR,
    )
    send_push_notification(patient, title="Sinal de alerta identificado", body=RED_FLAG_CONTEXTUAL_SAFETY_MESSAGE_PT_BR)
    for professional_user_id in assigned_professional_user_ids(db, patient.id):
        create_notification(
            db,
            user_id=professional_user_id,
            kind=NotificationKindEnum.RED_FLAG_SYMPTOM,
            message=(
                f"{patient.name} relatou um sintoma ({category_label}) que, considerando o "
                f"histórico de \"{risk_factor_label}\", pode indicar risco aumentado. "
                "Recomendamos contato o quanto antes."
            ),
        )


def notify_symptom_combination_alert(db: Session, *, patient: User, rule_label: str) -> None:
    """Called by the scheduler's _fire_symptom_combination_alert
    (bot/scheduler.py) when one of the LARANJA-tier ORANGE_COMBINATION_RULES
    (red_flag_symptoms.py) matches the patient's recent check-in history --
    a specific, named clinical association (e.g. persistent abdominal pain
    + weight loss) built up across separate days, not something any single
    day's report would catch on its own. Same dual-notify shape as
    notify_red_flag_symptom: always notifies the patient directly (a
    calmer, non-urgent tone -- see RED_FLAG_ORANGE_SAFETY_MESSAGE_PT_BR --
    since this is "worth a short-term evaluation", not an emergency), plus
    any assigned professional(s), named with which specific combination
    matched."""
    create_notification(
        db,
        user_id=patient.id,
        kind=NotificationKindEnum.SYMPTOM_CLUSTER_ALERT,
        message=RED_FLAG_ORANGE_SAFETY_MESSAGE_PT_BR,
    )
    send_push_notification(patient, title="Padrão de sinais identificado", body=RED_FLAG_ORANGE_SAFETY_MESSAGE_PT_BR)
    for professional_user_id in assigned_professional_user_ids(db, patient.id):
        create_notification(
            db,
            user_id=professional_user_id,
            kind=NotificationKindEnum.SYMPTOM_CLUSTER_ALERT,
            message=(
                f'{patient.name} apresentou, ao longo dos últimos check-ins, um padrão clínico '
                f'("{rule_label}") que pode merecer avaliação em curto prazo. Recomendamos considerar '
                "uma consulta."
            ),
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
