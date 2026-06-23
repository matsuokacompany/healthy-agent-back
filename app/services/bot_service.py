import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models.models import User
from app.services.daily_report_service import DailyReportService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotResponse:
    text: str
    ask_followup: bool = False


class BotService:
    """Orquestra fluxo de mensagens sem depender de canal específico."""

    def __init__(self, daily_report_service: DailyReportService | None = None):
        self.daily_report_service = daily_report_service or DailyReportService()

    def process_incoming(
        self,
        *,
        channel: Literal["whatsapp"],
        external_user_id: str,
        message_text: str,
    ) -> BotResponse:

        message_text = (message_text or "").strip()

        if not message_text:
            return BotResponse(text="")

        db = SessionLocal()

        try:
            user = (
                db.query(User)
                .filter(User.phone == external_user_id)
                .first()
            )

            if not user:
                return BotResponse(
                    text="Sua conta não está vinculada. Use o link de ativação no sistema."
                )

            db.refresh(user)

            status = self.daily_report_service.process_response(
                db,
                user,
                message_text,
            )

            return self._status_to_response(status)

        except SQLAlchemyError:
            logger.exception("Erro de banco no bot_service")
            return BotResponse(
                text="Não consegui salvar sua resposta agora. Tente novamente."
            )

        except Exception:
            logger.exception("Erro inesperado no bot_service")
            return BotResponse(
                text="Erro ao processar sua resposta. Tente novamente."
            )

        finally:
            db.close()

    def _status_to_response(self, status: str) -> BotResponse:

        if status == "NOT_AWAITING":
            return BotResponse(text="Você não possui um registro ativo no momento.")

        if status == "TOO_LONG":
            return BotResponse(text="Mensagem muito longa. Tente resumir.")

        if status == "EXPIRED":
            return BotResponse(text="Seu registro expirou. Aguarde o próximo envio.")

        if status in ("NEGATIVE", "COMPLETED"):
            return BotResponse(text="Perfeito! Informações registradas ✅")

        if status == "ASK_CAUSE":
            return BotResponse(
                text="Entendi. O que pode ter influenciado isso ontem?",
                ask_followup=True,
            )

        return BotResponse(text="Entendi. Obrigado pela resposta.")