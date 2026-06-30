import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.bot.channels.whatsapp_channel import WhatsAppBotChannel
from app.core.config import settings
from app.bot.scheduler import send_prompt
from app.bot.channels.bot_manager import BotManager
from app.models.models import CheckTypeEnum

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_whatsapp_signature(raw_body: bytes, signature: str | None) -> None:
    app_secret = settings.APP_SECRET
    if not app_secret:
        logger.error("APP_SECRET não configurado para validar webhook WhatsApp.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="whatsapp_signature_not_configured",
        )

    if not signature or not signature.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid WhatsApp signature",
        )

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid WhatsApp signature",
        )


@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(challenge)

    return {"error": "Verification failed"}


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
):
    raw_body = await request.body()
    verify_whatsapp_signature(raw_body, x_hub_signature_256)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    logger.info("WEBHOOK WhatsApp recebido")

    bot_manager = getattr(request.app.state, "bot_manager", None)

    if not bot_manager:
        logger.error("BotManager não inicializado.")
        raise HTTPException(status_code=500, detail="bot_manager_unavailable")

    channel = bot_manager.channels.get("whatsapp")

    if not channel:
        logger.error("Canal WhatsApp não registrado.")
        raise HTTPException(status_code=500, detail="whatsapp_channel_unavailable")

    # 🔥 SEM FILTRO PREMATURO
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
