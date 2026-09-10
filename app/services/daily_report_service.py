from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.models.models import (
    CheckTypeEnum,
    DailyReport,
    DailyReportStatusEnum,
    MedicationAdherenceLevelEnum,
    MonitoringPlan,
    User,
)
from app.core.config import settings
from app.services.clinical_data_service import ClinicalDataService
from app.services.notification_service import notify_red_flag_symptom, notify_symptom_reported
from app.services.red_flag_detection_service import RedFlagDetectionService
from app.services.red_flag_symptoms import RedFlagCategory
from app.services.supplement_service import SupplementService
from app.services.symptom_normalization_service import SymptomNormalizationService


class DailyReportService:
    MAX_TEXT_LENGTH = 280
    RESPONSE_WINDOW_HOURS = 24

    @classmethod
    def create_pending_report(
        cls,
        db: Session,
        *,
        user: User,
        monitoring_plan: MonitoringPlan,
        check_type: CheckTypeEnum,
        now: datetime | None = None,
        report_date: date | None = None,
    ) -> DailyReport:
        now = now or datetime.now(timezone.utc)
        report_date = report_date or now.date()
        report = (
            db.query(DailyReport)
            .filter(DailyReport.monitoring_plan_id == monitoring_plan.id)
            .filter(DailyReport.report_date == report_date)
            .filter(DailyReport.check_type == check_type)
            .first()
        )

        if report is None:
            report = DailyReport(
                user_id=user.id,
                monitoring_plan_id=monitoring_plan.id,
                report_date=report_date,
                check_type=check_type,
                prompt_sent_at=now,
                expires_at=now + timedelta(hours=cls.RESPONSE_WINDOW_HOURS),
            )
            db.add(report)
        elif report.status != DailyReportStatusEnum.EXPIRED:
            return report

        report.user_id = user.id
        report.symptom_description = None
        report.symptom_description_encryption_envelope = None
        report.suspected_cause = None
        report.suspected_cause_encryption_envelope = None
        report.had_symptoms = None
        report.diet_adherence = None
        report.exercise_adherence = None
        report.medication_adherence = None
        report.medication_adherence_level = None
        report.red_flag_category = None
        report.lifestyle_notes = None
        report.lifestyle_notes_encryption_envelope = None
        report.completed = False
        report.awaiting_response = True
        report.awaiting_cause = False
        report.status = DailyReportStatusEnum.PENDING
        report.prompt_sent_at = now
        report.expires_at = now + timedelta(hours=cls.RESPONSE_WINDOW_HOURS)

        db.flush()
        return report

    @classmethod
    def process_response(cls, db: Session, user: User, message_text: str) -> str:
        message_text = (message_text or "").strip()

        if len(message_text) > cls.MAX_TEXT_LENGTH:
            return "TOO_LONG"

        report = cls._get_open_report(db, user)
        if not report:
            return "NOT_AWAITING"

        now = datetime.now(timezone.utc)
        if cls._is_expired(report, now):
            report.awaiting_response = False
            report.awaiting_cause = False
            report.completed = False
            report.status = DailyReportStatusEnum.EXPIRED
            db.commit()
            return "EXPIRED"

        if report.completed or report.status == DailyReportStatusEnum.COMPLETED:
            return "ALREADY_COMPLETED"

        if report.awaiting_cause or report.status == DailyReportStatusEnum.AWAITING_CAUSE:
            cls._write_clinical(report, suspected_cause=None)
            report.awaiting_cause = False
            report.awaiting_response = False
            report.completed = True
            report.status = DailyReportStatusEnum.COMPLETED
            db.commit()
            return "COMPLETED"

        if report.status == DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION:
            cls._write_clinical(report, symptom_description=message_text, suspected_cause=None)
            notify_symptom_reported(db, patient=user, report=report)
            red_flag = RedFlagDetectionService.detect(message_text)
            if red_flag:
                notify_red_flag_symptom(db, patient=user, category_label=red_flag.label)
            result = cls._finish_symptom_flow(db, report, red_flag=red_flag)
            SymptomNormalizationService.normalize(db, report, message_text)
            return result

        if report.status == DailyReportStatusEnum.AWAITING_DIET_ADHERENCE:
            # Deterministic WhatsApp interactive buttons (see
            # BotService._translate's "ASK_DIET_ADHERENCE" message) — the
            # tap comes back as one of the diet_yes/diet_no markers added to
            # _is_positive_response/_is_negative_response below.
            if cls._is_negative_response(message_text):
                report.diet_adherence = False
                report.awaiting_response = True
                report.status = DailyReportStatusEnum.AWAITING_DIET_DEVIATION_DESCRIPTION
                db.commit()
                return "ASK_DIET_DEVIATION"
            if cls._is_positive_response(message_text):
                report.diet_adherence = True
            # An unrecognized answer just skips ahead rather than blocking
            # completion on a retry loop -- same tradeoff as the rest of
            # this flow (see the marker fallback comment below).
            return cls._ask_exercise_adherence(db, report)

        if report.status == DailyReportStatusEnum.AWAITING_DIET_DEVIATION_DESCRIPTION:
            cls._write_clinical(report, lifestyle_notes=message_text)
            return cls._ask_exercise_adherence(db, report)

        if report.status == DailyReportStatusEnum.AWAITING_EXERCISE_ADHERENCE:
            if cls._is_negative_response(message_text):
                report.exercise_adherence = False
            elif cls._is_positive_response(message_text):
                report.exercise_adherence = True
            return cls._ask_medication_adherence(db, report)

        if report.status == DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE:
            level = cls._parse_medication_response(message_text)
            if level is not None:
                report.medication_adherence_level = level
                report.medication_adherence = level == MedicationAdherenceLevelEnum.ALL.value
            report.awaiting_response = False
            report.completed = True
            report.status = DailyReportStatusEnum.COMPLETED
            db.commit()
            return "COMPLETED"

        if not report.awaiting_response:
            return "NOT_AWAITING"

        if cls._is_negative_response(message_text):
            report.had_symptoms = False
            cls._write_clinical(report, symptom_description=None, suspected_cause=None)
            return cls._finish_symptom_flow(db, report)

        if cls._is_positive_response(message_text):
            report.had_symptoms = True
            cls._write_clinical(report, symptom_description=None)
            report.awaiting_response = True
            report.awaiting_cause = False
            report.status = DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION
            db.commit()
            return "ASK_SYMPTOM_DESCRIPTION"

        report.had_symptoms = True
        cls._write_clinical(report, symptom_description=message_text, suspected_cause=None)
        notify_symptom_reported(db, patient=user, report=report)
        red_flag = RedFlagDetectionService.detect(message_text)
        if red_flag:
            notify_red_flag_symptom(db, patient=user, category_label=red_flag.label)
        result = cls._finish_symptom_flow(db, report, red_flag=red_flag)
        SymptomNormalizationService.normalize(db, report, message_text)
        return result

    @classmethod
    def _finish_symptom_flow(cls, db: Session, report: DailyReport, *, red_flag: RedFlagCategory | None = None) -> str:
        """Ends the symptom portion of the daily check-in.

        Defers completion for every plan (self-service and professional-led
        alike) to ask about diet, exercise, and medication/supplement
        adherence — deterministic WhatsApp interactive-button questions
        (diet, then exercise, then medication; see BotService._translate) in
        the same conversation, instead of a separate template message per
        question (see README "Otimização de custo do WhatsApp"). All of
        these questions are about the report's day (yesterday, from the
        patient's point of view — see app/bot/scheduler.py's report_date).

        `red_flag` records whether RedFlagDetectionService matched this
        check-in's description against a reviewed category (see
        red_flag_symptoms.py) and switches the returned status so
        BotService._translate prepends the safety message to the very next
        bot reply in this same WhatsApp conversation, instead of it waiting
        in a notification the patient might not see in time.
        """
        report.awaiting_response = True
        report.awaiting_cause = False
        report.completed = False
        report.status = DailyReportStatusEnum.AWAITING_DIET_ADHERENCE
        report.red_flag_category = red_flag.key if red_flag else None
        db.commit()
        return "ASK_DIET_ADHERENCE_RED_FLAG" if red_flag else "ASK_DIET_ADHERENCE"

    @classmethod
    def _ask_exercise_adherence(cls, db: Session, report: DailyReport) -> str:
        report.awaiting_response = True
        report.status = DailyReportStatusEnum.AWAITING_EXERCISE_ADHERENCE
        db.commit()
        return "ASK_EXERCISE_ADHERENCE"

    @classmethod
    def _ask_medication_adherence(cls, db: Session, report: DailyReport) -> str:
        # Only ask if the patient (or their professional) actually has at
        # least one currently-active supplement/medication registered on the
        # platform -- nothing registered, or every course already finished
        # (SupplementService.is_active), means there's nothing to ask about.
        supplements = SupplementService(db).list_for_patient(report.user_id)
        if not SupplementService.list_active_names(supplements):
            report.awaiting_response = False
            report.completed = True
            report.status = DailyReportStatusEnum.COMPLETED
            db.commit()
            return "COMPLETED"

        report.awaiting_response = True
        report.status = DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE
        db.commit()
        return "ASK_MEDICATION_ADHERENCE"

    @classmethod
    def update_patient_response(
        cls,
        db: Session,
        report: DailyReport,
        *,
        had_symptoms: bool | None = None,
        symptom_description: str | None = None,
        diet_adherence: bool | None = None,
        exercise_adherence: bool | None = None,
        medication_adherence: bool | None = None,
        medication_adherence_level: str | None = None,
        lifestyle_notes: str | None = None,
    ) -> DailyReport:
        if had_symptoms is True:
            symptom_description = (symptom_description or "").strip()
            if not symptom_description:
                raise ValueError("A symptom description is required when symptoms are reported")

        report.had_symptoms = had_symptoms
        report.diet_adherence = diet_adherence
        report.exercise_adherence = exercise_adherence
        report.medication_adherence = medication_adherence
        # A caller that knows the finer-grained level (the monitoring page's
        # edit UI) passes it directly; one that only knows the boolean (any
        # older caller) gets it derived 1:1 -- ALL/NONE, no PARTIAL, same as
        # what that boolean alone could ever represent.
        if medication_adherence_level is not None:
            report.medication_adherence_level = medication_adherence_level
        elif medication_adherence is True:
            report.medication_adherence_level = MedicationAdherenceLevelEnum.ALL.value
        elif medication_adherence is False:
            report.medication_adherence_level = MedicationAdherenceLevelEnum.NONE.value
        else:
            report.medication_adherence_level = None
        cls._write_clinical(
            report,
            symptom_description=symptom_description if had_symptoms is not False else None,
            # Cause collection is retired. Editing a report also erases any
            # legacy value that predates this API version.
            suspected_cause=None,
            lifestyle_notes=lifestyle_notes or None,
        )
        report.completed = True
        report.awaiting_response = False
        report.awaiting_cause = False
        report.status = DailyReportStatusEnum.COMPLETED
        # A professional/patient editing a report through the platform gets
        # the same red-flag safety net as the WhatsApp flow -- there's no
        # "next bot reply" to prepend a message to here, but the in-app
        # notification (to the patient and any assigned professional)
        # still applies. Editing away from "had symptoms" clears a
        # previously-detected category, same as the term links below.
        red_flag = RedFlagDetectionService.detect(symptom_description) if had_symptoms is True else None
        report.red_flag_category = red_flag.key if red_flag else None
        if had_symptoms is True:
            notify_symptom_reported(db, patient=report.user, report=report)
            if red_flag:
                notify_red_flag_symptom(db, patient=report.user, category_label=red_flag.label)
        db.commit()
        if had_symptoms is True:
            SymptomNormalizationService.normalize(db, report, symptom_description)
        else:
            # Editing away from "had symptoms" invalidates any term links
            # from the description that used to be here.
            SymptomNormalizationService.clear(db, report)
        db.refresh(report)
        return cls.hydrate_clinical(report)

    @classmethod
    def delete_patient_response(cls, db: Session, report: DailyReport) -> DailyReport:
        report.had_symptoms = None
        report.diet_adherence = None
        report.exercise_adherence = None
        report.medication_adherence = None
        report.medication_adherence_level = None
        report.red_flag_category = None
        cls._write_clinical(report, symptom_description=None, suspected_cause=None, lifestyle_notes=None)
        report.completed = False
        report.awaiting_response = True
        report.awaiting_cause = False
        report.status = DailyReportStatusEnum.PENDING
        db.commit()
        SymptomNormalizationService.clear(db, report)
        db.refresh(report)
        return report

    @classmethod
    def _get_open_report(cls, db: Session, user: User) -> DailyReport | None:
        return (
            db.query(DailyReport)
            .filter(DailyReport.user_id == user.id)
            .filter(DailyReport.completed.is_(False))
            .filter(
                DailyReport.status.in_(
                    [
                        DailyReportStatusEnum.PENDING,
                        DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION,
                        DailyReportStatusEnum.AWAITING_CAUSE,
                        DailyReportStatusEnum.AWAITING_DIET_ADHERENCE,
                        DailyReportStatusEnum.AWAITING_DIET_DEVIATION_DESCRIPTION,
                        DailyReportStatusEnum.AWAITING_EXERCISE_ADHERENCE,
                        DailyReportStatusEnum.AWAITING_MEDICATION_ADHERENCE,
                    ]
                )
            )
            .order_by(DailyReport.created_at.desc(), DailyReport.id.desc())
            .first()
        )

    _UNSET = object()

    @classmethod
    def _write_clinical(
        cls,
        report: DailyReport,
        *,
        symptom_description=_UNSET,
        suspected_cause=_UNSET,
        lifestyle_notes=_UNSET,
    ) -> None:
        if settings.CLINICAL_ENCRYPTION_PROVIDER == "disabled" and settings.ENV != "production":
            if symptom_description is not cls._UNSET:
                report.symptom_description = symptom_description
                report.symptom_description_encryption_envelope = None
            if suspected_cause is not cls._UNSET:
                report.suspected_cause = suspected_cause
                report.suspected_cause_encryption_envelope = None
            if lifestyle_notes is not cls._UNSET:
                report.lifestyle_notes = lifestyle_notes
                report.lifestyle_notes_encryption_envelope = None
            return

        clinical_data = ClinicalDataService()
        if symptom_description is not cls._UNSET:
            clinical_data.write_text(report, "symptom_description", symptom_description)
        if suspected_cause is not cls._UNSET:
            clinical_data.write_text(report, "suspected_cause", suspected_cause)
        if lifestyle_notes is not cls._UNSET:
            clinical_data.write_text(report, "lifestyle_notes", lifestyle_notes)

    @classmethod
    def hydrate_clinical(cls, report: DailyReport, clinical_data: ClinicalDataService | None = None) -> DailyReport:
        if not (
            report.symptom_description_encryption_envelope
            or report.suspected_cause_encryption_envelope
            or report.lifestyle_notes_encryption_envelope
        ):
            return report
        clinical_data = clinical_data or ClinicalDataService()
        if report.symptom_description_encryption_envelope:
            set_committed_value(
                report,
                "symptom_description",
                clinical_data.read_text(report, "symptom_description"),
            )
        if report.suspected_cause_encryption_envelope:
            set_committed_value(
                report,
                "suspected_cause",
                clinical_data.read_text(report, "suspected_cause"),
            )
        if report.lifestyle_notes_encryption_envelope:
            set_committed_value(
                report,
                "lifestyle_notes",
                clinical_data.read_text(report, "lifestyle_notes"),
            )
        return report

    @staticmethod
    def _is_expired(report: DailyReport, now: datetime) -> bool:
        expires_at = report.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at < now

    @staticmethod
    def _normalize_button_text(message_text: str) -> str:
        return (
            message_text.lower()
            .strip()
            .replace("ã", "a")
            .replace("á", "a")
            .replace("à", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("õ", "o")
            .replace("ú", "u")
            .replace("ç", "c")
        )

    @classmethod
    def _parse_medication_response(cls, message_text: str) -> str | None:
        """Tri-state answer to the medication/supplement question -- ALL,
        PARTIAL, or NONE. Kept separate from _is_positive_response/
        _is_negative_response (which only have a binary notion of "yes"/
        "no") because more than one registered supplement adds a real
        middle answer (see BotService._translate's ASK_MEDICATION_ADHERENCE).
        The legacy medication_yes/medication_no marker checks below are for
        an in-flight conversation that was sent the old two-button message
        right before this change deployed.
        """
        normalized = cls._normalize_button_text(message_text)
        if "medication_all" in normalized or "medication_yes" in normalized:
            return MedicationAdherenceLevelEnum.ALL.value
        if "medication_partial" in normalized:
            return MedicationAdherenceLevelEnum.PARTIAL.value
        if "medication_none" in normalized or "medication_no" in normalized:
            return MedicationAdherenceLevelEnum.NONE.value
        if cls._is_positive_response(message_text):
            return MedicationAdherenceLevelEnum.ALL.value
        if cls._is_negative_response(message_text):
            return MedicationAdherenceLevelEnum.NONE.value
        return None

    @classmethod
    def _is_positive_response(cls, message_text: str) -> bool:
        normalized = cls._normalize_button_text(message_text)
        positive_markers = (
            "sim",
            "tive sintomas",
            "tive sintoma",
            "symptoms_yes",
            "sintomas_sim",
            "tive_sintomas",
            "diet_yes",
            "exercise_yes",
            "medication_yes",
        )
        return normalized in positive_markers or any(marker in normalized for marker in positive_markers)

    @classmethod
    def _is_negative_response(cls, message_text: str) -> bool:
        normalized = cls._normalize_button_text(message_text)
        negative_markers = (
            "nao",
            "nao tive",
            "nao tive sintomas",
            "sem sintomas",
            "nenhum sintoma",
            "estou bem",
            "tudo bem",
            "symptoms_no",
            "sintomas_nao",
            "nao_tive_sintomas",
            "diet_no",
            "exercise_no",
            "medication_no",
        )
        return normalized in negative_markers or any(marker in normalized for marker in negative_markers)
