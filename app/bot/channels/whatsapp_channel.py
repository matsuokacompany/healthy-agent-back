import logging
from datetime import date

import httpx

from app.core.config import settings
from app.bot.channels.base import BaseBotChannel
from app.services.bot_service import BotService
from app.models.models import User, CheckTypeEnum

logger = logging.getLogger(__name__)


class WhatsAppBotChannel(BaseBotChannel):
    def __init__(self, bot_service: BotService | None = None):
        self.bot_service = bot_service or BotService()

        self.base_url = (
            f"https://graph.facebook.com/v23.0/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )

    # =========================================================
    # ENVIO DE TEXTO (respostas do bot)
    # =========================================================
    async def send_message(self, user_id: str, text: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": user_id,
            "type": "text",
            "text": {"body": text},
        }

        await self._post(payload)

    # =========================================================
    # ENVIO DE TEMPLATE (INÍCIO DO FLUXO)
    # =========================================================
    async def send_template(
        self,
        user: User,
        check_type: CheckTypeEnum,
        report_date: date | None = None,
    ) -> None:
        """
        Template oficial do WhatsApp (Meta API).
        Aqui começa o fluxo real do sistema.
        """

        if not user.phone:
            logger.warning("Usuário sem telefone | user_id=%s", user.id)
            return

        template_name = settings.WHATSAPP_DAILY_TEMPLATE_NAME
        formatted_report_date = report_date.strftime("%d/%m/%Y") if report_date else ""

        payload = {
            "messaging_product": "whatsapp",
            "to": user.phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "pt_BR"
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": user.name or "Usuário"
                            },
                            {
                                "type": "text",
                                "text": formatted_report_date
                            }
                        ]
                    }
                ]
            }
        }

        await self._post(payload)

    # =========================================================
    # HTTP CORE
    # =========================================================
    async def _post(self, payload: dict) -> None:
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.base_url,
                json=payload,
                headers=headers,
            )

        logger.info(
            "WhatsApp API status=%s response=%s",
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

    # =========================================================
    # WEBHOOK (INBOUND)
    # =========================================================
    def _extract_messages(self, payload: dict) -> list[dict]:
        messages = []

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                if "messages" not in value:
                    continue

                messages.extend(value.get("messages", []))

        return messages

    async def handle_incoming(self, payload: dict) -> None:
        logger.info(
            "Webhook WhatsApp recebido | keys=%s",
            list(payload.keys()),
        )

        messages = self._extract_messages(payload)

        if not messages:
            logger.info("Webhook ignorado (sem mensagens reais)")
            return

        for message in messages:
            external_user_id = str(message.get("from", "")).strip()
            message_type = message.get("type")

            text = ""

            if message_type == "text":
                text = (message.get("text") or {}).get("body", "").strip()

            elif message_type == "button":
                text = (message.get("button") or {}).get("payload", "").strip()

            elif message_type == "interactive":
                interactive = message.get("interactive") or {}
                button_reply = interactive.get("button_reply") or {}
                list_reply = interactive.get("list_reply") or {}
                text = (
                    button_reply.get("id")
                    or button_reply.get("title")
                    or list_reply.get("id")
                    or list_reply.get("title")
                    or ""
                ).strip()

            else:
                logger.warning("Tipo não suportado: %s", message_type)
                continue

            if not external_user_id or not text:
                logger.warning("Mensagem inválida: %s", message)
                continue

            response = self.bot_service.process_incoming(
                channel="whatsapp",
                external_user_id=external_user_id,
                message_text=text,
            )

            if response.text:
                await self.send_message(
                    external_user_id,
                    response.text,
                )

            logger.info(
                "Mensagem processada | from=%s | response=%s",
                external_user_id,
                response.text,
            )