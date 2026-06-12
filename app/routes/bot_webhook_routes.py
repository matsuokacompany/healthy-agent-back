import logging
import os
from fastapi import APIRouter, Request

from app.bot.channels.whatsapp_channel import WhatsAppBotChannel

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


@router.post('/webhook/whatsapp')
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    logger.info('Webhook WhatsApp recebido no endpoint /webhook/whatsapp')

    bot_manager = getattr(request.app.state, 'bot_manager', None)
    if not bot_manager:
        logger.error('BotManager não inicializado na aplicação.')
        return {'status': 'error', 'detail': 'bot_manager_unavailable'}

    channel: WhatsAppBotChannel = bot_manager.channels.get('whatsapp')
    if not channel:
        logger.error('Canal WhatsApp não registrado no BotManager.')
        return {'status': 'error', 'detail': 'whatsapp_channel_unavailable'}

    await channel.handle_incoming(payload)
    return {'status': 'ok'}

@router.post("/debug/send-prompt")
async def debug_send_prompt():
    from app.bot.scheduler import send_prompt
    from app.bot.channels.bot_manager import BotManager
    from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
    from app.models.models import CheckTypeEnum
    import asyncio

    bm = BotManager()
    bm.register_channel("whatsapp", WhatsAppBotChannel())

    await send_prompt(bm, CheckTypeEnum.MORNING)

    return {"status": "ok"}