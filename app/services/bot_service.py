import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db.session import SessionLocal
from app.models.models import User, WhatsAppMessage
from app.services.daily_report_service import DailyReportService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotResponse:
    text: str
    ask_followup: bool = False
    duplicate: bool = False


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
        message_id: str,
    ) -> BotResponse:

        message_text = (message_text or "").strip()
        message_id = (message_id or "").strip()

        if not message_text:
            return BotResponse(text="")

        db = SessionLocal()

        try:
            normalized_user_id = self._normalize_wa_id(external_user_id)
            webhook_message = self._reserve_message(
                db,
                message_id=message_id,
                channel=channel,
                external_user_id=external_user_id,
                normalized_user_id=normalized_user_id,
            )
            if webhook_message is None:
                return BotResponse(text="", duplicate=True)

            user = self._find_user_by_whatsapp_identity(db, external_user_id, normalized_user_id)

            if not user:
                logger.warning(
                    "WhatsApp user not linked | wa_id=%s normalized_wa_id=%s message_id=%s",
                    self._mask_phone(external_user_id),
                    self._mask_phone(normalized_user_id),
                    message_id,
                )
                response = BotResponse(
                    text="Conta não vinculada. Acesse o sistema para ativar seu acesso."
                )
                self._mark_message_processed(db, webhook_message, response)
                return response

            webhook_message.user_id = user.id
            logger.info(
                "WhatsApp user linked | user_id=%s wa_id=%s stored_wa_id=%s stored_phone=%s message_id=%s",
                user.id,
                self._mask_phone(normalized_user_id),
                self._mask_phone(user.whatsapp_wa_id),
                self._mask_phone(user.phone),
                message_id,
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

            response = self._translate(status)
            self._mark_message_processed(db, webhook_message, response)
            return response

        except SQLAlchemyError:
            db.rollback()
            logger.exception("DB error no BotService")
            return BotResponse(
                text="Não consegui processar sua resposta agora. Tente novamente."
            )

        except Exception:
            db.rollback()
            logger.exception("Erro inesperado no BotService")
            return BotResponse(
                text="Erro ao processar mensagem. Tente novamente."
            )

        finally:
            db.close()


    @classmethod
    def _reserve_message(
        cls,
        db,
        *,
        message_id: str,
        channel: str,
        external_user_id: str,
        normalized_user_id: str | None,
    ) -> WhatsAppMessage | None:
        if not message_id:
            raise ValueError("WhatsApp message missing id")

        existing = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == message_id).first()
        if existing:
            logger.info("Duplicate WhatsApp message ignored | message_id=%s", message_id)
            return None

        webhook_message = WhatsAppMessage(
            message_id=message_id,
            channel=channel,
            external_user_id=external_user_id,
            normalized_user_id=normalized_user_id,
            status="PROCESSING",
        )
        db.add(webhook_message)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info("Duplicate WhatsApp message ignored after unique constraint | message_id=%s", message_id)
            return None
        return webhook_message

    @staticmethod
    def _mark_message_processed(db, webhook_message: WhatsAppMessage, response: BotResponse) -> None:
        webhook_message.status = "PROCESSED"
        webhook_message.response_text = response.text
        webhook_message.processed_at = datetime.now(timezone.utc)
        db.commit()

    @classmethod
    def _find_user_by_whatsapp_identity(
        cls,
        db,
        external_user_id: str,
        normalized_wa_id: str | None,
    ) -> User | None:
        if not normalized_wa_id:
            return None

        user = db.query(User).filter(User.whatsapp_wa_id == normalized_wa_id).first()
        if user:
            return user

        # Compatibility path for existing users created before whatsapp_wa_id existed.
        # This is a one-time indexed lookup by stored phone variants, then the Meta
        # wa_id is persisted as the durable identity for future webhooks. It
        # intentionally does not scan all users.
        lookup_values = {external_user_id, normalized_wa_id}
        lookup_values.update(cls._phone_lookup_variants(normalized_wa_id))
        candidates = db.query(User).filter(User.phone.in_(lookup_values)).limit(2).all()
        if not candidates:
            normalized_phone_column = cls._normalized_phone_column(User.phone)
            candidates = (
                db.query(User)
                .filter(User.phone.isnot(None))
                .filter(normalized_phone_column.in_(lookup_values))
                .limit(2)
                .all()
            )

        if len(candidates) != 1:
            if len(candidates) > 1:
                logger.warning(
                    "WhatsApp wa_id compatibility lookup ambiguous | wa_id=%s candidate_count=%s",
                    cls._mask_phone(normalized_wa_id),
                    len(candidates),
                )
            return None

        user = candidates[0]
        user.whatsapp_wa_id = normalized_wa_id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.warning(
                "WhatsApp wa_id already linked to another user | user_id=%s wa_id=%s",
                user.id,
                cls._mask_phone(normalized_wa_id),
            )
            return None

        logger.info(
            "WhatsApp wa_id linked by legacy phone compatibility | user_id=%s wa_id=%s stored_phone=%s",
            user.id,
            cls._mask_phone(normalized_wa_id),
            cls._mask_phone(user.phone),
        )
        return user

    @staticmethod
    def _normalized_phone_column(column):
        normalized = column
        for char in ("+", "(", ")", "-", " ", "."):
            normalized = func.replace(normalized, char, "")
        return normalized

    @classmethod
    def _phone_lookup_variants(cls, phone: str | None) -> set[str]:
        normalized = cls._normalize_phone(phone)
        if not normalized:
            return set()

        variants = {normalized}
        # Brazilian mobile numbers may appear in WhatsApp Cloud API webhooks with or
        # without the extra ninth digit after country code (55) + area code. This is
        # only used for one-time legacy linking; whatsapp_wa_id is the primary key.
        if normalized.startswith("55") and len(normalized) == 13 and normalized[4] == "9":
            variants.add(normalized[:4] + normalized[5:])
        elif normalized.startswith("55") and len(normalized) == 12:
            variants.add(normalized[:4] + "9" + normalized[4:])

        return variants

    @staticmethod
    def _normalize_wa_id(wa_id: str | None) -> str | None:
        return BotService._normalize_phone(wa_id)

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