import logging
from fastapi import APIRouter, Request

from app.bot.channels.whatsapp_channel import WhatsAppBotChannel

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == "SEU_VERIFY_TOKEN":
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
