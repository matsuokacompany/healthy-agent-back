import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.models import DailyReport, User

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 280


def is_negative(message: str) -> bool:
    negatives = [
        "não",
        "nao",
        "nenhum",
        "nenhuma",
        "não tive",
        "nao tive",
        "sem sintomas"
    ]

    message = message.lower().strip()
    return any(n in message for n in negatives)


class DailyReportService:

    @staticmethod
    def process_response(db: Session, user: User, message: str):

        message = message.strip()

        if len(message) > MAX_INPUT_CHARS:
            return "TOO_LONG"

        if not user.current_report_id:
            return "NOT_AWAITING"

        report = db.query(DailyReport).filter(
            DailyReport.id == user.current_report_id
        ).first()

        if not report:
            user.current_report_id = None
            db.commit()
            return "INVALID_STATE"

        # ⏳ Timeout 24h
        delta = datetime.now(timezone.utc) - report.created_at
        if delta > timedelta(hours=24):
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