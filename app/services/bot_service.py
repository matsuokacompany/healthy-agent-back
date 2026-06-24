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
    """
    Camada de orquestração leve:
    - resolve usuário
    - chama serviço de domínio
    - traduz status em resposta de UX
    """

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
            normalized_user_id = self._normalize_phone(external_user_id)
            user = (
                db.query(User)
                .filter(User.phone.in_([external_user_id, normalized_user_id]))
                .first()
            )

            if not user:
                return BotResponse(
                    text="Conta não vinculada. Acesse o sistema para ativar seu acesso."
                )

            status = self.daily_report_service.process_response(
                db,
                user,
                message_text,
            )

            return self._translate(status)

        except SQLAlchemyError:
            logger.exception("DB error no BotService")
            return BotResponse(
                text="Não consegui processar sua resposta agora. Tente novamente."
            )

        except Exception:
            logger.exception("Erro inesperado no BotService")
            return BotResponse(
                text="Erro ao processar mensagem. Tente novamente."
            )

        finally:
            db.close()

    # =========================================================
    # TRADUÇÃO DE STATUS → UX
    # =========================================================
    def _translate(self, status: str) -> BotResponse:

        if status == "NEGATIVE":
            return BotResponse(
                text="Perfeito 👍 Obrigado por informar. Se sentir qualquer alteração, estamos por aqui."
            )

        if status == "ASK_SYMPTOM_DESCRIPTION":
            return BotResponse(
                text=(
                    "Entendi. Quais sintomas você teve ontem?\n\n"
                    "Descreva em poucas palavras. Máx: 280 caracteres."
                ),
                ask_followup=True,
            )

        if status == "ASK_CAUSE":
            return BotResponse(
                text=(
                    "Entendi.\n\n"
                    "Agora me diga o que você acha que pode ter causado isso.\n"
                    "Exemplo: alimentação, estresse, sono, atividade física...\n\n"
                    "Máx: 280 caracteres."
                ),
                ask_followup=True,
            )

        if status == "COMPLETED":
            return BotResponse(
                text="Registro concluído com sucesso ✅ Obrigado pelas informações."
            )

        if status == "NOT_AWAITING":
            return BotResponse(
                text="Essa solicitação já foi encerrada ou expirou. Aguarde o próximo check-in."
            )

        if status == "TOO_LONG":
            return BotResponse(
                text="Mensagem muito longa. Tente resumir em até 280 caracteres."
            )

        if status == "INVALID_STATE":
            return BotResponse(
                text="Houve um problema de contexto. Vamos reiniciar o registro no próximo check-in."
            )

        if status == "ALREADY_COMPLETED":
            return BotResponse(
                text="Esse registro já foi finalizado 👍"
            )

        return BotResponse(
            text="Entendi. Obrigado pela resposta."
        )