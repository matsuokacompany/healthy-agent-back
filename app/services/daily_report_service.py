from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.models import CheckTypeEnum, DailyReport, DailyReportStatusEnum, MonitoringPlan, User


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
        report.suspected_cause = None
        report.had_symptoms = None
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
            report.suspected_cause = message_text
            report.awaiting_cause = False
            report.awaiting_response = False
            report.completed = True
            report.status = DailyReportStatusEnum.COMPLETED
            db.commit()
            return "COMPLETED"

        if report.status == DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION:
            report.symptom_description = message_text
            report.awaiting_response = False
            report.awaiting_cause = True
            report.status = DailyReportStatusEnum.AWAITING_CAUSE
            db.commit()
            return "ASK_CAUSE"

        if not report.awaiting_response:
            return "NOT_AWAITING"

        if cls._is_negative_response(message_text):
            report.had_symptoms = False
            report.symptom_description = None
            report.suspected_cause = None
            report.awaiting_response = False
            report.awaiting_cause = False
            report.completed = True
            report.status = DailyReportStatusEnum.COMPLETED
            db.commit()
            return "NEGATIVE"

        if cls._is_positive_response(message_text):
            report.had_symptoms = True
            report.symptom_description = None
            report.awaiting_response = True
            report.awaiting_cause = False
            report.status = DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION
            db.commit()
            return "ASK_SYMPTOM_DESCRIPTION"

        report.had_symptoms = True
        report.symptom_description = message_text
        report.awaiting_response = False
        report.awaiting_cause = True
        report.status = DailyReportStatusEnum.AWAITING_CAUSE
        db.commit()
        return "ASK_CAUSE"

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
                    ]
                )
            )
            .order_by(DailyReport.created_at.desc(), DailyReport.id.desc())
            .first()
        )

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
    def _is_positive_response(cls, message_text: str) -> bool:
        normalized = cls._normalize_button_text(message_text)
        positive_markers = (
            "sim",
            "tive sintomas",
            "tive sintoma",
            "symptoms_yes",
            "sintomas_sim",
            "tive_sintomas",
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
        )
        return normalized in negative_markers or any(marker in normalized for marker in negative_markers)
