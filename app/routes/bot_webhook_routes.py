import logging
from fastapi import APIRouter, Request

from app.bot.channels.whatsapp_channel import WhatsAppBotChannel

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post('/webhook/whatsapp')
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    logger.info('Webhook WhatsApp recebido no endpoint /webhook/whatsapp')

    channel: WhatsAppBotChannel = request.app.state.bot_manager.channels.get('whatsapp')
    if not channel:
        logger.error('Canal WhatsApp não registrado no BotManager.')
        return {'status': 'error', 'detail': 'whatsapp_channel_unavailable'}

    await channel.handle_incoming(payload)
    return {'status': 'ok'}
