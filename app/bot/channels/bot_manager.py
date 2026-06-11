import logging
from typing import Any

from app.models.models import User

logger = logging.getLogger(__name__)


class BotManager:
    """
    Gerencia canais de envio e decide qual usar por usuário.

    Ordem de prioridade padrão:
    1. Telegram
    2. WhatsApp
    """

    def __init__(self, channels: dict[str, Any] | None = None):
        self.channels = channels or {}

        # ordem explícita = previsibilidade
        self.channel_priority = ["telegram", "whatsapp"]

    # =========================================================
    # REGISTRO
    # =========================================================

    def register_channel(self, channel_name: str, channel: Any) -> None:
        logger.info("Registrando canal: %s", channel_name)
        self.channels[channel_name] = channel

    # =========================================================
    # DECISÃO DE CANAL
    # =========================================================

    def resolve_channel_name_for_user(self, user: User) -> str | None:
        """
        Decide o melhor canal disponível para o usuário.
        """

        available_channels = []

        if user.telegram_id and "telegram" in self.channels:
            available_channels.append("telegram")

        if user.phone and "whatsapp" in self.channels:
            available_channels.append("whatsapp")

        if not available_channels:
            logger.warning(
                "Usuário sem canais disponíveis | user_id=%s",
                user.id
            )
            return None

        # escolhe baseado na prioridade
        for channel in self.channel_priority:
            if channel in available_channels:
                logger.debug(
                    "Canal escolhido=%s | user_id=%s",
                    channel,
                    user.id
                )
                return channel

        return available_channels[0]

    # =========================================================
    # ACESSO AO CANAL
    # =========================================================

    def get_channel_for_user(self, user: User):
        channel_name = self.resolve_channel_name_for_user(user)

        if not channel_name:
            return None

        return self.channels.get(channel_name)

    # =========================================================
    # DEBUG UTIL
    # =========================================================

    def get_user_channel_debug(self, user: User) -> dict:
        return {
            "user_id": user.id,
            "telegram_available": bool(user.telegram_id and "telegram" in self.channels),
            "whatsapp_available": bool(user.phone and "whatsapp" in self.channels),
            "chosen_channel": self.resolve_channel_name_for_user(user),
        }