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
    return any(k in message.lower().strip() for k in NEGATIVE_KEYWORDS)


class DailyReportService:
    """Fluxo determinístico de Daily Report com controle de estado explícito."""

    @staticmethod
    def process_response(db: Session, user: User, message: str):
        try:
            message = (message or "").strip()

            if len(message) == 0:
                return "INVALID"

            if len(message) > MAX_INPUT_CHARS:
                return "TOO_LONG"

            # 🔒 Sem contexto ativo
            if not user.current_report_id and not user.pending_check_type:
                return "NOT_AWAITING"

            # =========================
            # 🔵 INÍCIO DE FLUXO NOVO
            # =========================
            if not user.current_report_id:

                prompt_sent_at = user.pending_prompt_sent_at

                if prompt_sent_at and prompt_sent_at.tzinfo is None:
                    prompt_sent_at = prompt_sent_at.replace(tzinfo=timezone.utc)

                # timeout de 24h do prompt
                if prompt_sent_at and datetime.now(timezone.utc) - prompt_sent_at > timedelta(hours=24):
                    user.pending_check_type = None
                    user.pending_report_date = None
                    user.pending_prompt_sent_at = None
                    db.commit()
                    return "EXPIRED"

                # resposta negativa encerra fluxo
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

                # resposta positiva cria report e entra no estado "aguardando causa"
                report = DailyReport(
                    user_id=user.id,
                    check_type=user.pending_check_type,
                    report_date=user.pending_report_date,
                    had_symptoms=True,
                    symptom_description=message,
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
            # 🔵 FLUXO EXISTENTE
            # =========================

            report = db.query(DailyReport).filter(
                DailyReport.id == user.current_report_id,
                DailyReport.user_id == user.id,
            ).first()

            if not report:
                user.current_report_id = None
                db.commit()
                return "INVALID_STATE"

            # timeout do report
            created_at = report.created_at
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            if created_at and datetime.now(timezone.utc) - created_at > timedelta(hours=24):
                user.current_report_id = None
                db.commit()
                return "EXPIRED"

            # =========================
            # 🔥 GUARD PRINCIPAL (ANTI BUG)
            # =========================

            # já finalizado
            if report.completed:
                return "ALREADY_COMPLETED"

            # =========================
            # 🔵 ETAPA 1: sintoma
            # =========================
            if not report.symptom_description:
                if is_negative(message):
                    report.completed = True
                    db.commit()

                    user.current_report_id = None
                    return "NEGATIVE"

                report.symptom_description = message
                report.had_symptoms = True

                db.commit()
                return "ASK_CAUSE"

            # =========================
            # 🔵 ETAPA 2: causa
            # =========================
            if not report.suspected_cause:
                report.suspected_cause = message
                report.completed = True

                db.commit()

                user.current_report_id = None
                return "COMPLETED"

            # estado inconsistente (idempotência)
            return "ALREADY_COMPLETED"

        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Erro de banco ao processar daily report. user_id=%s",
                user.id,
            )
            raise