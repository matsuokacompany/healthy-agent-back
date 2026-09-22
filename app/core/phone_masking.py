def mask_phone(phone: str | None) -> str | None:
    """Last-4-digits phone mask for log lines -- shared by BotService and
    the bot channels so a phone number never reaches logs unmasked
    regardless of which layer is doing the logging.
    """
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"***{digits[-4:]}"
