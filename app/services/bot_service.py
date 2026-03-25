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
    """Orquestra fluxo de mensagens sem depender do canal de transporte."""

    def __init__(self, daily_report_service: DailyReportService | None = None):
        self.daily_report_service = daily_report_service or DailyReportService()

    def process_incoming(
        self,
        *,
        channel: Literal["telegram", "whatsapp"],
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
            user = self._load_user(db=db, channel=channel, external_user_id=external_user_id)
            if not user:
                logger.warning(
                    "Usuário não encontrado para mensagem recebida. channel=%s external_user_id=%s",
                    channel,
                    external_user_id,
                )
                return BotResponse(text="Sua conta não está vinculada. Use /start SEU_CODIGO.")

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
            return BotResponse(text="Não consegui salvar sua resposta agora. Tente novamente em instantes.")
        except Exception:
            logger.exception(
                "Erro inesperado ao processar mensagem. channel=%s external_user_id=%s",
                channel,
                external_user_id,
            )
            return BotResponse(text="Ocorreu um erro ao processar sua resposta. Tente novamente.")
        finally:
            db.close()

    @staticmethod
    def _load_user(db, *, channel: str, external_user_id: str) -> User | None:
        if channel == "telegram":
            return db.query(User).filter(User.telegram_id == external_user_id).first()

        if channel == "whatsapp":
            return db.query(User).filter(User.phone == external_user_id).first()

        return None

    @staticmethod
    def _status_to_response(status: str) -> BotResponse:
        if status == "NOT_AWAITING":
            return BotResponse(text="Você não possui um registro pendente hoje.")
        if status == "TOO_LONG":
            return BotResponse(text="Mensagem muito longa. Tente reduzir para 280 caracteres.")
        if status == "EXPIRED":
            return BotResponse(text="Seu registro expirou. Espere o próximo prompt.")
        if status == "NEGATIVE":
            return BotResponse(text="Perfeito 👍 Nenhum sintoma registrado hoje.")
        if status == "ASK_CAUSE":
            return BotResponse(
                text=(
                    "Entendi. Agora me diga: o que você fez de diferente ontem? "
                    "(algo que possa ter causado o sintoma)"
                ),
                ask_followup=True,
            )
        if status == "COMPLETED":
            return BotResponse(text="Perfeito! Suas informações foram registradas ✅")

        return BotResponse(text="Entendi. Obrigado pela resposta.")
