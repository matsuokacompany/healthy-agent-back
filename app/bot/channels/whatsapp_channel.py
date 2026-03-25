import logging

from app.bot.channels.base import BaseBotChannel
from app.services.bot_service import BotService

logger = logging.getLogger(__name__)


class WhatsAppBotChannel(BaseBotChannel):
    def __init__(self, bot_service: BotService | None = None):
        self.bot_service = bot_service or BotService()

    async def send_message(self, user_id: str, text: str) -> None:
        logger.info(
            "Envio WhatsApp solicitado para user_id=%s, mas integração de provider não configurada.",
            user_id,
        )

    async def handle_incoming(self, payload) -> None:
        logger.info("Recebido webhook WhatsApp. keys=%s", list(payload.keys()))

        messages = payload.get("messages") or []
        if not messages:
            logger.warning("Webhook WhatsApp sem mensagens processáveis.")
            return

        for message in messages:
            external_user_id = str(message.get("from", "")).strip()
            text = (message.get("text") or {}).get("body", "").strip()

            if not external_user_id or not text:
                logger.warning("Mensagem WhatsApp ignorada por falta de from/text. payload=%s", message)
                continue

            response = self.bot_service.process_incoming(
                channel="whatsapp",
                external_user_id=external_user_id,
                message_text=text,
            )
            logger.info(
                "Mensagem WhatsApp processada para from=%s. resposta='%s'",
                external_user_id,
                response.text,
            )
