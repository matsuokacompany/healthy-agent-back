import logging

from app.models.models import User

logger = logging.getLogger(__name__)


class BotManager:
    """Decide qual canal usar por usuário para envios ativos."""

    def __init__(self, channels: dict[str, object] | None = None):
        self.channels = channels or {}

    def register_channel(self, channel_name: str, channel: object) -> None:
        logger.info("Registrando canal de bot: %s", channel_name)
        self.channels[channel_name] = channel

    def resolve_channel_name_for_user(self, user: User) -> str | None:
        if user.telegram_id and "telegram" in self.channels:
            return "telegram"

        if user.phone and "whatsapp" in self.channels:
            return "whatsapp"

        logger.warning("Nenhum canal disponível para user_id=%s", user.id)
        return None

    def get_channel_for_user(self, user: User):
        channel_name = self.resolve_channel_name_for_user(user)
        if not channel_name:
            return None
        return self.channels[channel_name]
