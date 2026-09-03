"""Minimal backend-originated transactional email, over plain smtplib.

Separate from Supabase Auth's own emails (signup confirmation, password
recovery) — those go through Supabase's own SMTP configuration and templates.
This is for notifications the backend decides to send on its own, like a
patient link request.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD and settings.SMTP_FROM_EMAIL)


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    attachment: tuple[bytes, str, str] | None = None,
) -> bool:
    """Best-effort send — logs and returns False on failure rather than
    raising, so a notification email never blocks the action that triggered it.

    `attachment`, when given, is (content, filename, content_type) — e.g. a
    screenshot on a support contact message.
    """
    if not is_configured():
        logger.warning("SMTP not configured; skipping email | subject=%s", subject)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to
    message.set_content(body)

    if attachment:
        content, filename, content_type = attachment
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(content, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=filename)

    try:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as client:
            client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            client.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send email | subject=%s", subject)
        return False
