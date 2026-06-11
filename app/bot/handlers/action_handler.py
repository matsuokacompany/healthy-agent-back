import logging

logger = logging.getLogger(__name__)


# =========================================================
# PLACEHOLDER (Telegram desativado)
# =========================================================

async def start(*args, **kwargs):
    logger.info("Telegram desativado - start ignorado")
    return None


async def ask_symptom(*args, **kwargs):
    logger.info("Telegram desativado - ask_symptom ignorado")
    return None


async def ask_action(*args, **kwargs):
    logger.info("Telegram desativado - ask_action ignorado")
    return None


async def cancel(*args, **kwargs):
    logger.info("Telegram desativado - cancel ignorado")
    return None


# =========================================================
# HANDLER REGISTRATION (NO-OP)
# =========================================================

def register_action_handler(app):
    logger.info("Telegram ConversationHandler desativado (noop)")
    return