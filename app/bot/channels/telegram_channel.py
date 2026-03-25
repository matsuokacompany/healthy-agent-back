import logging

from app.bot.channels.base import BaseBotChannel
from app.services.bot_service import BotService

logger = logging.getLogger(__name__)


class TelegramBotChannel(BaseBotChannel):
    def __init__(self, telegram_app, bot_service: BotService | None = None):
        self.telegram_app = telegram_app
        self.bot_service = bot_service or BotService()

    async def send_message(self, user_id: str, text: str) -> None:
        logger.info("Enviando mensagem Telegram para user_id=%s", user_id)
        await self.telegram_app.bot.send_message(chat_id=user_id, text=text)

    async def handle_incoming(self, payload):
        user_id = payload["user_id"]
        text = payload.get("text", "")
        reply = payload["reply"]

        logger.info("Recebido payload Telegram. user_id=%s", user_id)
        response = self.bot_service.process_incoming(
            channel="telegram",
            external_user_id=user_id,
            message_text=text,
        )
        await reply(response.text)
        return response
