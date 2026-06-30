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
            user = self._find_user_by_phone(db, external_user_id, normalized_user_id)

            if not user:
                logger.warning(
                    "WhatsApp user not linked | external_user_id=%s normalized_user_id=%s",
                    self._mask_phone(external_user_id),
                    self._mask_phone(normalized_user_id),
                )
                return BotResponse(
                    text="Conta não vinculada. Acesse o sistema para ativar seu acesso."
                )

            logger.info(
                "WhatsApp user linked | user_id=%s external_user_id=%s normalized_user_id=%s stored_phone=%s",
                user.id,
                self._mask_phone(external_user_id),
                self._mask_phone(normalized_user_id),
                self._mask_phone(user.phone),
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

    @classmethod
    def _find_user_by_phone(cls, db, external_user_id: str, normalized_user_id: str | None) -> User | None:
        lookup_values = {external_user_id}
        lookup_values.update(cls._phone_lookup_variants(normalized_user_id))

        user = db.query(User).filter(User.phone.in_(lookup_values)).first()
        if user or not normalized_user_id:
            return user

        # Fallback for legacy rows saved with punctuation/spaces before phone normalization existed.
        for candidate in db.query(User).filter(User.phone.isnot(None)).all():
            stored_variants = cls._phone_lookup_variants(cls._normalize_phone(candidate.phone))
            if stored_variants & lookup_values:
                logger.info(
                    "WhatsApp user matched by normalized stored phone | user_id=%s external_user_id=%s stored_phone=%s",
                    candidate.id,
                    cls._mask_phone(external_user_id),
                    cls._mask_phone(candidate.phone),
                )
                return candidate

        return None

    @classmethod
    def _phone_lookup_variants(cls, phone: str | None) -> set[str]:
        normalized = cls._normalize_phone(phone)
        if not normalized:
            return set()

        variants = {normalized}
        # Brazilian mobile numbers may appear in WhatsApp Cloud API webhooks with or
        # without the extra ninth digit after country code (55) + area code.
        if normalized.startswith("55") and len(normalized) == 13 and normalized[4] == "9":
            variants.add(normalized[:4] + normalized[5:])
        elif normalized.startswith("55") and len(normalized) == 12:
            variants.add(normalized[:4] + "9" + normalized[4:])

        return variants

    @staticmethod
    def _normalize_phone(phone: str | None) -> str | None:
        if not phone:
            return None
        return "".join(ch for ch in phone if ch.isdigit())

    @staticmethod
    def _mask_phone(phone: str | None) -> str | None:
        if not phone:
            return None
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) <= 4:
            return "*" * len(digits)
        return f"***{digits[-4:]}"

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