import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models.models import DailyReport, User

logger = logging.getLogger(__name__)
MAX_INPUT_CHARS = 280

NEGATIVE_KEYWORDS = [
    "não", "nao", "nenhum", "nenhuma", "não tive", "nao tive", "sem sintomas"
]


def is_negative(message: str) -> bool:
    message = message.lower().strip()
    return any(k in message for k in NEGATIVE_KEYWORDS)


class DailyReportService:
    """Gerencia o fluxo de respostas do DailyReport (sintoma + causa)"""

    @staticmethod
    def process_response(db: Session, user: User, message: str):
        try:
            message = message.strip()

            if len(message) > MAX_INPUT_CHARS:
                return "TOO_LONG"

            if not user.current_report_id:
                if not user.pending_check_type:
                    return "NOT_AWAITING"

                prompt_sent_at = user.pending_prompt_sent_at
                if prompt_sent_at and prompt_sent_at.tzinfo is None:
                    prompt_sent_at = prompt_sent_at.replace(tzinfo=timezone.utc)

                if prompt_sent_at and datetime.now(timezone.utc) - prompt_sent_at > timedelta(hours=24):
                    user.pending_check_type = None
                    user.pending_report_date = None
                    user.pending_prompt_sent_at = None
                    db.commit()
                    return "EXPIRED"

                if is_negative(message):
                    report = DailyReport(
                        user_id=user.id,
                        check_type=user.pending_check_type,
                        report_date=user.pending_report_date,
                        had_symptoms=False,
                        completed=True,
                    )
                    db.add(report)
                    user.pending_check_type = None
                    user.pending_report_date = None
                    user.pending_prompt_sent_at = None
                    db.commit()
                    return "NEGATIVE"

                report = DailyReport(
                    user_id=user.id,
                    check_type=user.pending_check_type,
                    report_date=user.pending_report_date,
                    had_symptoms=True,
                    symptom_description=message,
                )
                db.add(report)
                db.flush()
                user.current_report_id = report.id
                user.pending_check_type = None
                user.pending_report_date = None
                user.pending_prompt_sent_at = None
                db.commit()
                return "ASK_CAUSE"

            report = db.query(DailyReport).filter(
                DailyReport.id == user.current_report_id,
                DailyReport.user_id == user.id,
            ).first()

            if not report:
                user.current_report_id = None
                db.commit()
                return "INVALID_STATE"

            # ⏳ Timeout 24h
            report_created_at = report.created_at
            if report_created_at and report_created_at.tzinfo is None:
                report_created_at = report_created_at.replace(tzinfo=timezone.utc)

            if report_created_at and datetime.now(timezone.utc) - report_created_at > timedelta(hours=24):
                user.current_report_id = None
                db.commit()
                return "EXPIRED"

            # 🟢 PRIMEIRA RESPOSTA (Sintoma)
            if not report.symptom_description:
                if is_negative(message):
                    report.completed = True
                    user.current_report_id = None
                    db.commit()
                    return "NEGATIVE"

                report.symptom_description = message
                report.had_symptoms = True
                db.commit()
                return "ASK_CAUSE"

            # 🔵 SEGUNDA RESPOSTA (Causa suspeita)
            if not report.suspected_cause:
                report.suspected_cause = message
                report.completed = True
                user.current_report_id = None
                db.commit()
                return "COMPLETED"

            return "ALREADY_COMPLETED"
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Erro de banco ao processar daily report. user_id=%s", user.id)
            raise
