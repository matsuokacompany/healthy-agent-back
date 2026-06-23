import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.models import DailyReport, User

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 280
WINDOW_HOURS = 24

NEGATIVE_KEYWORDS = [
    "não", "nao", "nenhum", "nenhuma", "não tive", "nao tive", "sem sintomas"
]


def is_negative(message: str) -> bool:
    return any(k in message.lower().strip() for k in NEGATIVE_KEYWORDS)


class DailyReportService:
    """
    Fluxo baseado em JANELA DE TEMPLATE:
    - pending_prompt_sent_at define validade
    - current_report_id define etapa ativa
    """

    @staticmethod
    def _is_window_valid(user: User) -> bool:
        if not user.pending_prompt_sent_at:
            return False

        now = datetime.now(timezone.utc)
        sent_at = user.pending_prompt_sent_at

        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)

        return now - sent_at <= timedelta(hours=WINDOW_HOURS)

    @staticmethod
    def process_response(db: Session, user: User, message: str):
        try:
            message = (message or "").strip()

            if not message:
                return "INVALID"

            if len(message) > MAX_INPUT_CHARS:
                return "TOO_LONG"

            # 🔒 fora da janela do template
            if not DailyReportService._is_window_valid(user):
                # limpa estado antigo para evitar ghost flow
                user.current_report_id = None
                user.pending_check_type = None
                user.pending_report_date = None
                user.pending_prompt_sent_at = None
                db.commit()
                return "NOT_AWAITING"

            # =========================
            # 🟢 INÍCIO DO FLUXO
            # =========================
            if not user.current_report_id:

                # resposta negativa → encerra fluxo direto
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

                # resposta positiva → cria report
                report = DailyReport(
                    user_id=user.id,
                    check_type=user.pending_check_type,
                    report_date=user.pending_report_date,
                    symptom_description=message,
                    had_symptoms=True,
                    completed=False,
                )

                db.add(report)
                db.flush()

                user.current_report_id = report.id
                user.pending_check_type = None
                user.pending_report_date = None
                user.pending_prompt_sent_at = None

                db.commit()
                return "ASK_CAUSE"

            # =========================
            # 🔵 FLUXO ATIVO (CAUSA)
            # =========================
            report = db.query(DailyReport).filter(
                DailyReport.id == user.current_report_id,
                DailyReport.user_id == user.id,
            ).first()

            if not report:
                user.current_report_id = None
                db.commit()
                return "INVALID_STATE"

            # segurança extra
            if report.completed:
                return "ALREADY_COMPLETED"

            # etapa 2: causa
            if not report.suspected_cause:
                report.suspected_cause = message
                report.completed = True

                user.current_report_id = None

                db.commit()
                return "COMPLETED"

            return "ALREADY_COMPLETED"

        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Erro de banco ao processar daily report. user_id=%s",
                user.id,
            )
            raise