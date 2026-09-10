import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, or_, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.security_context import set_database_service_context
from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    DailyReportSymptomTerm,
    MedicationAdherenceLevelEnum,
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    Notification,
    NotificationKindEnum,
    Subscription,
    SymptomTerm,
    User,
)
from app.services.daily_report_service import DailyReportService
from app.services.dunning_service import DunningService
from app.services.notification_service import (
    notify_checkin_pending,
    notify_medication_adherence_none,
    notify_patient_inactive,
    notify_supplement_course_ended,
    notify_symptom_cluster,
    notify_symptom_pattern,
)
from app.services.payment_service import subscription_grants_access
from app.services.red_flag_symptoms import CUMULATIVE_SYMPTOM_CLUSTERS
from app.services.supplement_service import SupplementService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
SCHEDULER_ADVISORY_LOCK_ID = 2026063001
DUNNING_ADVISORY_LOCK_ID = 2026063002
CHECKIN_REMINDER_ADVISORY_LOCK_ID = 2026063003
SUPPLEMENT_NOTIFICATION_ADVISORY_LOCK_ID = 2026063004
MONITORING_ALERTS_ADVISORY_LOCK_ID = 2026063005

# Days of consecutive incomplete check-ins that trigger an inactivity alert --
# only these two exact streak lengths fire, so the alert lands once when it
# first becomes worth attention and once as a single escalation, never as a
# daily repeat for as long as the patient stays silent.
INACTIVITY_ALERT_DAYS = (3, 7)
# One deeper than the longest threshold above -- see _fire_inactivity_alert.
INACTIVITY_LOOKBACK_REPORTS = max(INACTIVITY_ALERT_DAYS) + 1
SYMPTOM_PATTERN_MIN_OCCURRENCES = 3
SYMPTOM_PATTERN_WINDOW_DAYS = 7
SYMPTOM_PATTERN_COOLDOWN_DAYS = 7
# Cooldown is kind-level (like SYMPTOM_PATTERN_COOLDOWN_DAYS above), not
# per-cluster -- fine today with a single cluster in CUMULATIVE_SYMPTOM_CLUSTERS;
# revisit if a second cluster is added and both need to be able to fire
# independently within the same window.
CUMULATIVE_SYMPTOM_COOLDOWN_DAYS = 14


def _mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"***{digits[-4:]}"


def _is_postgresql_session(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _try_acquire_scheduler_lock(db, lock_id: int = SCHEDULER_ADVISORY_LOCK_ID) -> bool:
    if not _is_postgresql_session(db):
        logger.warning(
            "Scheduler advisory lock skipped because database dialect is not PostgreSQL | dialect=%s",
            db.get_bind().dialect.name,
        )
        return True

    return bool(
        db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        ).scalar()
    )


def _release_scheduler_lock(db, lock_id: int = SCHEDULER_ADVISORY_LOCK_ID) -> None:
    if not _is_postgresql_session(db):
        return

    db.execute(
        text("SELECT pg_advisory_unlock(:lock_id)"),
        {"lock_id": lock_id},
    )


async def send_prompt(bot_manager, check_type: CheckTypeEnum) -> None:
    logger.info("SEND_PROMPT START | type=%s", check_type.value)

    db = SessionLocal()
    set_database_service_context(db, "scheduler")
    plans_processed = 0
    plans_skipped = 0
    plans_failed = 0
    lock_acquired = False

    try:
        lock_acquired = _try_acquire_scheduler_lock(db)
        if not lock_acquired:
            logger.info("SEND_PROMPT SKIPPED | type=%s reason=advisory_lock_busy", check_type.value)
            return

        tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        now = datetime.now(tz)
        today = now.date()
        report_date = today - timedelta(days=1)
        now_utc = now.astimezone(timezone.utc)

        plans = (
            db.query(MonitoringPlan)
            .join(User, MonitoringPlan.patient_id == User.id)
            .filter(MonitoringPlan.active.is_(True))
            .filter(or_(MonitoringPlan.start_date.is_(None), MonitoringPlan.start_date <= report_date))
            .filter(or_(MonitoringPlan.end_date.is_(None), MonitoringPlan.end_date >= report_date))
            .filter(User.phone.isnot(None))
            .all()
        )

        for plan in plans:
            user = plan.patient
            try:
                if plan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value:
                    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
                    if not subscription_grants_access(subscription):
                        plans_skipped += 1
                        continue

                channel = bot_manager.get_channel_for_user(user)
                if not channel or not user.phone:
                    plans_skipped += 1
                    continue

                report = DailyReportService.create_pending_report(
                    db=db,
                    user=user,
                    monitoring_plan=plan,
                    check_type=check_type,
                    now=now_utc,
                    report_date=report_date,
                )
                if report.completed:
                    db.rollback()
                    plans_skipped += 1
                    continue

                db.commit()
                db.refresh(report)

                wa_id = await channel.send_template(
                    user=user,
                    check_type=check_type,
                    report_date=report.report_date,
                )

                if wa_id and user.whatsapp_wa_id != wa_id:
                    user.whatsapp_wa_id = wa_id
                    db.commit()
                    logger.info(
                        "WhatsApp wa_id stored from send_template response | user_id=%s wa_id=%s",
                        user.id,
                        _mask_identifier(wa_id),
                    )

                plans_processed += 1

            except Exception:
                db.rollback()
                plans_failed += 1
                logger.exception("ERROR monitoring_plan_id=%s user_id=%s", plan.id, user.id if user else None)

    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_prompt")

    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db)
            except Exception:
                logger.exception("Failed to release scheduler advisory lock")
        db.close()

    logger.info(
        "SEND_PROMPT DONE | sent=%s skipped=%s failed=%s",
        plans_processed,
        plans_skipped,
        plans_failed,
    )


async def run_dunning_reminders() -> None:
    logger.info("DUNNING_REMINDERS START")

    db = SessionLocal()
    lock_acquired = False
    try:
        lock_acquired = _try_acquire_scheduler_lock(db, DUNNING_ADVISORY_LOCK_ID)
        if not lock_acquired:
            logger.info("DUNNING_REMINDERS SKIPPED | reason=advisory_lock_busy")
            return

        result = DunningService(db).run_daily_reminders()
        logger.info("DUNNING_REMINDERS DONE | %s", result)
    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR run_dunning_reminders")
    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db, DUNNING_ADVISORY_LOCK_ID)
            except Exception:
                logger.exception("Failed to release dunning advisory lock")
        db.close()


async def send_checkin_reminders() -> None:
    """In-app (not WhatsApp) nudge for a check-in still open late in the
    day. Runs once daily, so a report only ever gets one reminder even
    though this iterates every still-open report for today."""
    logger.info("CHECKIN_REMINDERS START")

    db = SessionLocal()
    set_database_service_context(db, "scheduler")
    lock_acquired = False
    reminders_sent = 0

    try:
        lock_acquired = _try_acquire_scheduler_lock(db, CHECKIN_REMINDER_ADVISORY_LOCK_ID)
        if not lock_acquired:
            logger.info("CHECKIN_REMINDERS SKIPPED | reason=advisory_lock_busy")
            return

        tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        today = datetime.now(tz).date()

        pending_reports = (
            db.query(DailyReport)
            .filter(DailyReport.report_date == today)
            .filter(DailyReport.completed.is_(False))
            .filter(
                DailyReport.status.in_(
                    [
                        DailyReportStatusEnum.PENDING,
                        DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION,
                        DailyReportStatusEnum.AWAITING_CAUSE,
                        DailyReportStatusEnum.AWAITING_DIET_ADHERENCE,
                        DailyReportStatusEnum.AWAITING_DIET_DEVIATION_DESCRIPTION,
                        DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE,
                    ]
                )
            )
            .all()
        )

        for report in pending_reports:
            already_reminded_today = (
                db.query(Notification)
                .filter(
                    Notification.user_id == report.user_id,
                    Notification.kind == NotificationKindEnum.CHECKIN_PENDING.value,
                    Notification.created_at >= datetime.now(timezone.utc) - timedelta(hours=12),
                )
                .first()
            )
            if already_reminded_today:
                continue
            notify_checkin_pending(db, patient_user_id=report.user_id)
            reminders_sent += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_checkin_reminders")
    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db, CHECKIN_REMINDER_ADVISORY_LOCK_ID)
            except Exception:
                logger.exception("Failed to release checkin reminder advisory lock")
        db.close()

    logger.info("CHECKIN_REMINDERS DONE | sent=%s", reminders_sent)


async def send_supplement_course_ended_notifications() -> None:
    """Runs once daily. A duration-bound supplement already stops being
    named in the WhatsApp medication question once its course ends (see
    SupplementService.is_active) -- this is what actually tells the patient
    (and any assigned professionals) that it's done, exactly once per
    supplement (Supplement.ended_notification_sent_at)."""
    logger.info("SUPPLEMENT_COURSE_ENDED_NOTIFICATIONS START")

    db = SessionLocal()
    set_database_service_context(db, "scheduler")
    lock_acquired = False
    notified = 0

    try:
        lock_acquired = _try_acquire_scheduler_lock(db, SUPPLEMENT_NOTIFICATION_ADVISORY_LOCK_ID)
        if not lock_acquired:
            logger.info("SUPPLEMENT_COURSE_ENDED_NOTIFICATIONS SKIPPED | reason=advisory_lock_busy")
            return

        tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        today = datetime.now(tz).date()

        for supplement in SupplementService(db).list_courses_needing_end_notification(today):
            patient = db.query(User).filter(User.id == supplement.patient_id).first()
            if not patient:
                continue
            notify_supplement_course_ended(db, patient=patient, supplement=supplement)
            supplement.ended_notification_sent_at = datetime.now(timezone.utc)
            notified += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_supplement_course_ended_notifications")
    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db, SUPPLEMENT_NOTIFICATION_ADVISORY_LOCK_ID)
            except Exception:
                logger.exception("Failed to release supplement notification advisory lock")
        db.close()

    logger.info("SUPPLEMENT_COURSE_ENDED_NOTIFICATIONS DONE | notified=%s", notified)


def _fire_inactivity_alert(db, patient: User, recent_reports: list[DailyReport]) -> bool:
    # `recent_reports` is fetched one row deeper than the largest alert
    # threshold (see INACTIVITY_LOOKBACK) specifically so a streak that has
    # gone past every threshold reads as "longer than any of them" instead
    # of being clipped to the last one and re-firing it every day after.
    streak = 0
    for report in recent_reports:
        if report.completed:
            break
        streak += 1
    if streak not in INACTIVITY_ALERT_DAYS:
        return False
    notify_patient_inactive(db, patient=patient, days=streak)
    return True


def _fire_medication_alert(db, patient: User, recent_reports: list[DailyReport]) -> bool:
    completed = [report for report in recent_reports if report.completed]
    if len(completed) < 2:
        return False
    last_two = completed[:2]
    if any(report.medication_adherence_level != MedicationAdherenceLevelEnum.NONE.value for report in last_two):
        return False
    # Fire only the day the streak *reaches* two -- if the completed report
    # right before these two was already NONE too, this same alert would
    # already have fired on that earlier run.
    if len(completed) >= 3 and completed[2].medication_adherence_level == MedicationAdherenceLevelEnum.NONE.value:
        return False
    notify_medication_adherence_none(db, patient=patient)
    return True


def _fire_symptom_pattern_alert(db, patient: User, today) -> bool:
    already_notified = (
        db.query(Notification)
        .filter(
            Notification.user_id == patient.id,
            Notification.kind == NotificationKindEnum.SYMPTOM_PATTERN_ALERT.value,
            Notification.created_at >= datetime.now(timezone.utc) - timedelta(days=SYMPTOM_PATTERN_COOLDOWN_DAYS),
        )
        .first()
    )
    if already_notified:
        return False

    window_start = today - timedelta(days=SYMPTOM_PATTERN_WINDOW_DAYS - 1)
    occurrence_count = func.count(DailyReportSymptomTerm.daily_report_id.distinct())
    pattern = (
        db.query(SymptomTerm.label, occurrence_count)
        .join(DailyReportSymptomTerm, DailyReportSymptomTerm.symptom_term_id == SymptomTerm.id)
        .join(DailyReport, DailyReport.id == DailyReportSymptomTerm.daily_report_id)
        .filter(
            DailyReportSymptomTerm.patient_id == patient.id,
            DailyReport.report_date >= window_start,
            DailyReport.report_date <= today,
        )
        .group_by(SymptomTerm.label)
        .having(occurrence_count >= SYMPTOM_PATTERN_MIN_OCCURRENCES)
        .order_by(occurrence_count.desc())
        .first()
    )
    if not pattern:
        return False

    term_label, occurrences = pattern
    notify_symptom_pattern(db, patient=patient, term_label=term_label, occurrences=occurrences)
    return True


def _fire_symptom_cluster_alert(db, patient: User, today) -> bool:
    """Gated behind settings.CUMULATIVE_SYMPTOM_ALERTS_ENABLED (default off
    -- see CumulativeSymptomCluster's docstring in red_flag_symptoms.py for
    why). Unlike _fire_symptom_pattern_alert (same term repeated), this
    looks for DIFFERENT signs of the same clinical cluster spread across
    separate check-ins within the cluster's window -- a pattern that no
    single day's report, and no single RedFlagDetectionService call, would
    ever catch."""
    if not settings.CUMULATIVE_SYMPTOM_ALERTS_ENABLED:
        return False

    already_notified = (
        db.query(Notification)
        .filter(
            Notification.user_id == patient.id,
            Notification.kind == NotificationKindEnum.SYMPTOM_CLUSTER_ALERT.value,
            Notification.created_at >= datetime.now(timezone.utc) - timedelta(days=CUMULATIVE_SYMPTOM_COOLDOWN_DAYS),
        )
        .first()
    )
    if already_notified:
        return False

    for cluster in CUMULATIVE_SYMPTOM_CLUSTERS:
        window_start = today - timedelta(days=cluster.window_days - 1)
        term_labels = {
            label.lower()
            for (label,) in db.query(SymptomTerm.label)
            .join(DailyReportSymptomTerm, DailyReportSymptomTerm.symptom_term_id == SymptomTerm.id)
            .join(DailyReport, DailyReport.id == DailyReportSymptomTerm.daily_report_id)
            .filter(
                DailyReportSymptomTerm.patient_id == patient.id,
                DailyReport.report_date >= window_start,
                DailyReport.report_date <= today,
            )
            .distinct()
            .all()
        }
        if not term_labels:
            continue

        matched_signs = [
            sign for sign in cluster.signs if term_labels & {alias.lower() for alias in sign.aliases}
        ]
        if len(matched_signs) < cluster.min_distinct_signs:
            continue

        notify_symptom_cluster(
            db,
            patient=patient,
            cluster_label=cluster.label,
            matched_sign_labels=[sign.label for sign in matched_signs],
        )
        return True

    return False


async def send_monitoring_alerts() -> None:
    """Runs once daily. Reuses the daily check-in history to flag
    engagement/safety patterns worth attention: several missed check-ins in
    a row, medication adherence dropping to none, the same symptom
    recurring across the week, and -- gated behind
    settings.CUMULATIVE_SYMPTOM_ALERTS_ENABLED, see
    _fire_symptom_cluster_alert -- a defined group of different signs
    accumulating across a longer window. Goes to the patient's assigned
    professional(s) when there are any, otherwise to the patient themself
    (self-service plans have no professional to alert) -- see
    notification_service.py's notify_patient_inactive/
    notify_medication_adherence_none/notify_symptom_pattern/
    notify_symptom_cluster. Each rule fires once per crossing of its
    threshold, not on every day the pattern continues."""
    logger.info("MONITORING_ALERTS START")

    db = SessionLocal()
    set_database_service_context(db, "scheduler")
    lock_acquired = False
    alerts_sent = 0

    try:
        lock_acquired = _try_acquire_scheduler_lock(db, MONITORING_ALERTS_ADVISORY_LOCK_ID)
        if not lock_acquired:
            logger.info("MONITORING_ALERTS SKIPPED | reason=advisory_lock_busy")
            return

        tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        today = datetime.now(tz).date()

        plans = (
            db.query(MonitoringPlan)
            .filter(MonitoringPlan.active.is_(True))
            .filter(or_(MonitoringPlan.start_date.is_(None), MonitoringPlan.start_date <= today))
            .filter(or_(MonitoringPlan.end_date.is_(None), MonitoringPlan.end_date >= today))
            .all()
        )

        for plan in plans:
            patient = plan.patient
            if not patient:
                continue

            recent_reports = (
                db.query(DailyReport)
                .filter(DailyReport.monitoring_plan_id == plan.id)
                .order_by(DailyReport.report_date.desc())
                .limit(INACTIVITY_LOOKBACK_REPORTS)
                .all()
            )

            if _fire_inactivity_alert(db, patient, recent_reports):
                alerts_sent += 1
            if _fire_medication_alert(db, patient, recent_reports):
                alerts_sent += 1
            if _fire_symptom_pattern_alert(db, patient, today):
                alerts_sent += 1
            if _fire_symptom_cluster_alert(db, patient, today):
                alerts_sent += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("FATAL ERROR send_monitoring_alerts")
    finally:
        if lock_acquired:
            try:
                _release_scheduler_lock(db, MONITORING_ALERTS_ADVISORY_LOCK_ID)
            except Exception:
                logger.exception("Failed to release monitoring alerts advisory lock")
        db.close()

    logger.info("MONITORING_ALERTS DONE | sent=%s", alerts_sent)


def start_scheduler(bot_manager):
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)

    _scheduler = AsyncIOScheduler(
        timezone=tz,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 1800,
        },
    )

    _scheduler.add_job(
        send_prompt,
        CronTrigger(
            hour=settings.SCHEDULER_MORNING_HOUR,
            minute=settings.SCHEDULER_MORNING_MINUTE,
            timezone=tz,
        ),
        args=[bot_manager, CheckTypeEnum.MORNING],
        id="morning",
        replace_existing=True,
    )

    _scheduler.add_job(
        run_dunning_reminders,
        CronTrigger(hour=9, minute=0, timezone=tz),
        id="dunning_reminders",
        replace_existing=True,
    )

    _scheduler.add_job(
        send_checkin_reminders,
        CronTrigger(
            hour=settings.SCHEDULER_CHECKIN_REMINDER_HOUR,
            minute=settings.SCHEDULER_CHECKIN_REMINDER_MINUTE,
            timezone=tz,
        ),
        id="checkin_reminders",
        replace_existing=True,
    )

    _scheduler.add_job(
        send_supplement_course_ended_notifications,
        CronTrigger(hour=8, minute=30, timezone=tz),
        id="supplement_course_ended_notifications",
        replace_existing=True,
    )

    _scheduler.add_job(
        send_monitoring_alerts,
        CronTrigger(hour=8, minute=45, timezone=tz),
        id="monitoring_alerts",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler iniciado")

    return _scheduler


def stop_scheduler():
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    _scheduler = None


def get_scheduler():
    return _scheduler
