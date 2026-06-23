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
            "text": {"body": text},
        }

        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
            )

        logger.info(
            "WhatsApp send status=%s body=%s",
            response.status_code,
            response.text,
        )

        if response.status_code >= 400:
            logger.error(
                "Erro WhatsApp API status=%s body=%s",
                response.status_code,
                response.text,
            )

        response.raise_for_status()

    def _extract_messages(self, payload: dict) -> list[dict]:
        """
        Extrai apenas mensagens reais.
        Ignora statuses, deliveries, reads etc.
        """
        messages = []

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # 🔥 ponto crítico: ignora tudo que não for message
                if "messages" not in value:
                    continue

                messages.extend(value.get("messages", []))

        return messages

    async def handle_incoming(self, payload: dict) -> None:
        logger.info(
            "Webhook WhatsApp recebido. keys=%s",
            list(payload.keys()),
        )

        messages = self._extract_messages(payload)

        if not messages:
            logger.info(
                "Webhook ignorado (sem mensagens reais, apenas eventos de status)."
            )
            return

        for message in messages:
            external_user_id = str(message.get("from", "")).strip()
            message_type = message.get("type")

            text = ""

            if message_type == "text":
                text = (message.get("text") or {}).get("body", "").strip()

            elif message_type == "button":
                text = (message.get("button") or {}).get("payload", "").strip()

            else:
                logger.warning(
                    "Tipo de mensagem não suportado: %s | payload=%s",
                    message_type,
                    message,
                )
                continue

            if not external_user_id or not text:
                logger.warning(
                    "Mensagem ignorada (missing from/text). payload=%s",
                    message,
                )
                continue

            # 🚨 aqui está o "guard rail" principal:
            # só entra no bot_service se for mensagem REAL do usuário
            response = self.bot_service.process_incoming(
                channel="whatsapp",
                external_user_id=external_user_id,
                message_text=text,
            )

            await self.send_message(
                external_user_id,
                response.text,
            )

            logger.info(
                "Mensagem processada from=%s response='%s'",
                external_user_id,
                response.text,
            )