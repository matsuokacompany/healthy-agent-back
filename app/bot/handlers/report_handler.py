import logging

logger = logging.getLogger(__name__)


async def relatorio(*args, **kwargs):
    logger.info("Telegram desativado - relatorio ignorado")
    return None


async def relatorio_semanal(*args, **kwargs):
    logger.info("Telegram desativado - relatorio_semanal ignorado")
    return None


async def relatorio_mensal(*args, **kwargs):
    logger.info("Telegram desativado - relatorio_mensal ignorado")
    return None