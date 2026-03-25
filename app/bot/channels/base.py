from abc import ABC, abstractmethod
from typing import Any


class BaseBotChannel(ABC):
    @abstractmethod
    async def send_message(self, user_id: str, text: str) -> None:
        """Envia mensagem para usuário no canal."""

    @abstractmethod
    async def handle_incoming(self, payload: Any) -> None:
        """Processa payload recebido no canal."""
