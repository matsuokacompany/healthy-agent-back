import logging

import httpx

from app.core.config import settings
from app.bot.channels.base import BaseBotChannel
from app.services.bot_service import BotService

logger = logging.getLogger(__name__)


class WhatsAppBotChannel(BaseBotChannel):
    def __init__(self, bot_service: BotService | None = None):
        self.bot_service = bot_service or BotService()

    async def send_message(self, user_id: str, text: str) -> None:

        url = (
            f"https://graph.facebook.com/v23.0/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )

        payload = {
            "messaging_product": "whatsapp",
            "to": user_id,
            "type": "text",
            "text": {
                "body": text
            }
        }

        headers = {
            "Authorization": (
                f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
            ),
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers
            )

        logger.info(
            "WhatsApp status=%s body=%s",
            response.status_code,
            response.text
        )

        if response.status_code >= 400:
            logger.error(
                "Erro WhatsApp API status=%s body=%s",
                response.status_code,
                response.text,
            )

        response.raise_for_status()

    async def handle_incoming(self, payload) -> None:
        logger.info(
            "Recebido webhook WhatsApp. keys=%s",
            list(payload.keys())
        )

        messages = []

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages.extend(value.get("messages", []))

        if not messages:
            logger.warning(
                "Webhook WhatsApp sem mensagens processáveis."
            )
            return

        for message in messages:
            external_user_id = str(
                message.get("from", "")
            ).strip()

            text = (
                message.get("text") or {}
            ).get("body", "").strip()

            if not external_user_id or not text:
                logger.warning(
                    "Mensagem WhatsApp ignorada por falta de from/text. payload=%s",
                    message,
                )
                continue

            response = self.bot_service.process_incoming(
                channel="whatsapp",
                external_user_id=external_user_id,
                message_text=text,
            )

            await self.send_message(
                external_user_id,
                response.text
            )

            logger.info(
                "Mensagem WhatsApp processada para from=%s. resposta='%s'",
                external_user_id,
                response.text,
            )
