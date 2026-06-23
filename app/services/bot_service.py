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

        logger.info(
            "Processando mensagem. channel=%s user=%s chars=%s",
            channel,
            external_user_id,
            len(message_text),
        )

        # 🔥 proteção contra lixo/duplicata vazia
        if not message_text:
            logger.warning(
                "Mensagem vazia ignorada. channel=%s user=%s",
                channel,
                external_user_id,
            )
            return BotResponse(text="")

        db = SessionLocal()

        try:
            user = self._load_user(
                db=db,
                channel=channel,
                external_user_id=external_user_id,
            )

            if not user:
                logger.warning(
                    "Usuário não encontrado. channel=%s user=%s",
                    channel,
                    external_user_id,
                )
                return BotResponse(
                    text="Sua conta não está vinculada. Use o link de ativação no sistema."
                )

            status = self.daily_report_service.process_response(
                db,
                user,
                message_text,
            )

            logger.info(
                "Status gerado. user=%s status=%s",
                user.id,
                status,
            )

            return self._status_to_response(status, user)

        except SQLAlchemyError:
            logger.exception(
                "Erro de banco. user=%s",
                external_user_id,
            )
            return BotResponse(
                text="Não consegui salvar sua resposta agora. Tente novamente em instantes."
            )

        except Exception:
            logger.exception(
                "Erro inesperado. user=%s",
                external_user_id,
            )
            return BotResponse(
                text="Ocorreu um erro ao processar sua resposta. Tente novamente."
            )

        finally:
            db.close()

    @staticmethod
    def _load_user(db, *, channel: str, external_user_id: str) -> User | None:
        if channel == "whatsapp":
            return db.query(User).filter(User.phone == external_user_id).first()

        return None

    # 🔥 NOVA REGRA: só pergunta follow-up se houver contexto válido
    @staticmethod
    def _has_valid_context(user: User) -> bool:
        return bool(getattr(user, "has_pending_report", False))

    def _status_to_response(self, status: str, user: User) -> BotResponse:

        if status == "NOT_AWAITING":
            return BotResponse(text="Você não possui um registro pendente hoje.")

        if status == "TOO_LONG":
            return BotResponse(text="Mensagem muito longa. Tente reduzir o texto.")

        if status == "EXPIRED":
            return BotResponse(text="Seu registro expirou. Aguarde o próximo envio.")

        if status in ("NEGATIVE", "COMPLETED"):
            return BotResponse(text="Perfeito! Informações registradas ✅")

        # 🚨 PONTO CRÍTICO CORRIGIDO
        if status == "ASK_CAUSE":

            # só pergunta se existir contexto real
            if not self._has_valid_context(user):
                logger.warning(
                    "ASK_CAUSE bloqueado por falta de contexto. user=%s",
                    user.id,
                )
                return BotResponse(text="Perfeito! Informações registradas ✅")

            return BotResponse(
                text="Entendi. O que pode ter influenciado isso ontem?",
                ask_followup=True,
            )

        return BotResponse(text="Entendi. Obrigado pela resposta.")