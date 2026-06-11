import logging
from typing import Any

from app.models.models import User

logger = logging.getLogger(__name__)


class BotManager:
    """
    Gerencia canais de envio e decide qual usar por usuário.

    Canal ativo atual:
    - WhatsApp apenas
    """

    def __init__(self, channels: dict[str, Any] | None = None):
        self.channels = channels or {}

        # Apenas WhatsApp (sem Telegram)
        self.channel_priority = ["whatsapp"]

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
        Decide o canal disponível para o usuário.
        Telegram ignorado intencionalmente.
        """

        available_channels = []

        # ❌ Telegram removido do fluxo, mesmo que exista no DB
        # if user.telegram_id and "telegram" in self.channels:
        #     available_channels.append("telegram")

        if user.phone and "whatsapp" in self.channels:
            available_channels.append("whatsapp")

        if not available_channels:
            logger.warning(
                "Usuário sem canais disponíveis | user_id=%s",
                user.id
            )
            return None

        # só WhatsApp agora
        return "whatsapp"

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
            "telegram_available": False,  # forçado off
            "whatsapp_available": bool(user.phone and "whatsapp" in self.channels),
            "chosen_channel": self.resolve_channel_name_for_user(user),
        }