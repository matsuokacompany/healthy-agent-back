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
        channel: Literal["whatsapp"],  # Telegram removido
        external_user_id: str,
        message_text: str,
    ) -> BotResponse:
        logger.info(
            "Processando mensagem recebida. channel=%s external_user_id=%s chars=%s",
            channel,
            external_user_id,
            len(message_text or ""),
        )

        db = SessionLocal()
        try:
            user = self._load_user(
                db=db,
                channel=channel,
                external_user_id=external_user_id,
            )

            if not user:
                logger.warning(
                    "Usuário não encontrado. channel=%s external_user_id=%s",
                    channel,
                    external_user_id,
                )
                return BotResponse(
                    text="Sua conta não está vinculada. Use o link de ativação no sistema."
                )

            status = self.daily_report_service.process_response(db, user, message_text)

            logger.info(
                "Mensagem processada. channel=%s external_user_id=%s user_id=%s status=%s",
                channel,
                external_user_id,
                user.id,
                status,
            )

            return self._status_to_response(status)

        except SQLAlchemyError:
            logger.exception(
                "Erro de banco ao processar mensagem. channel=%s external_user_id=%s",
                channel,
                external_user_id,
            )
            return BotResponse(
                text="Não consegui salvar sua resposta agora. Tente novamente em instantes."
            )

        except Exception:
            logger.exception(
                "Erro inesperado ao processar mensagem. channel=%s external_user_id=%s",
                channel,
                external_user_id,
            )
            return BotResponse(
                text="Ocorreu um erro ao processar sua resposta. Tente novamente."
            )

        finally:
            db.close()

    @staticmethod
    def _load_user(db, *, channel: str, external_user_id: str) -> User | None:
        # Telegram removido do sistema
        if channel == "whatsapp":
            return db.query(User).filter(User.phone == external_user_id).first()

        return None

    @staticmethod
    def _status_to_response(status: str) -> BotResponse:
        if status == "NOT_AWAITING":
            return BotResponse(text="Você não possui um registro pendente hoje.")
        if status == "TOO_LONG":
            return BotResponse(text="Mensagem muito longa. Tente reduzir o texto.")
        if status == "EXPIRED":
            return BotResponse(text="Seu registro expirou. Aguarde o próximo envio.")
        if status == "NEGATIVE":
            return BotResponse(text="Perfeito! Informações registradas ✅")
        if status == "ASK_CAUSE":
            return BotResponse(
                text=(
                    "Entendi. O que pode ter influenciado isso ontem?"
                ),
                ask_followup=True,
            )
        if status == "COMPLETED":
            return BotResponse(text="Perfeito! Informações registradas ✅")

        return BotResponse(text="Entendi. Obrigado pela resposta.")