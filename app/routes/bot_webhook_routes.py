import logging
import os

from fastapi import APIRouter, Request, HTTPException

from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
from app.core.config import settings
from app.bot.scheduler import send_prompt
from app.bot.channels.bot_manager import BotManager
from app.models.models import CheckTypeEnum

logger = logging.getLogger(__name__)

router = APIRouter()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    return {"error": "Verification failed"}


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()

    logger.info("WEBHOOK RAW: %s", payload)
    logger.info("Webhook WhatsApp recebido no endpoint /webhook/whatsapp")

    # 🔥 Firewall leve: ignora eventos sem messages já no edge
    has_messages = any(
        "messages" in change.get("value", {})
        for entry in payload.get("entry", [])
        for change in entry.get("changes", [])
    )

    if not has_messages:
        logger.info("Webhook ignorado no router (sem messages reais).")
        return {"status": "ignored"}

    bot_manager = getattr(request.app.state, "bot_manager", None)
    if not bot_manager:
        logger.error("BotManager não inicializado na aplicação.")
        return {"status": "error", "detail": "bot_manager_unavailable"}

    channel: WhatsAppBotChannel = bot_manager.channels.get("whatsapp")
    if not channel:
        logger.error("Canal WhatsApp não registrado no BotManager.")
        return {"status": "error", "detail": "whatsapp_channel_unavailable"}

    await channel.handle_incoming(payload)

    return {"status": "ok"}


@router.post("/debug/send-prompt")
async def debug_send_prompt():
    # 🔒 proteção para não vazar em produção
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    bm = BotManager()
    bm.register_channel("whatsapp", WhatsAppBotChannel())

    await send_prompt(bm, CheckTypeEnum.MORNING)

    return {"status": "ok"}