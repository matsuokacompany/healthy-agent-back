import logging
from typing import Any

from app.models.models import User

logger = logging.getLogger(__name__)


class BotManager:
    """
    Gerencia canais de envio e decide qual usar por usuário.
    (atualmente: apenas WhatsApp)
    """

    def __init__(self, channels: dict[str, Any] | None = None):
        self.channels = channels or {}

    def register_channel(self, channel_name: str, channel: Any) -> None:
        logger.info("Registrando canal: %s", channel_name)
        self.channels[channel_name] = channel

    def resolve_channel_name_for_user(self, user: User) -> str | None:
        if user.phone and "whatsapp" in self.channels:
            return "whatsapp"

        logger.warning("Usuário sem canal disponível | user_id=%s", user.id)
        return None

    def get_channel_for_user(self, user: User):
        name = self.resolve_channel_name_for_user(user)
        return self.channels.get(name) if name else None

    def get_user_channel_debug(self, user: User) -> dict:
        return {
            "user_id": user.id,
            "whatsapp_available": bool(user.phone),
            "chosen_channel": self.resolve_channel_name_for_user(user),
        }