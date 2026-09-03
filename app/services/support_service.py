from fastapi import HTTPException, status

from app.core.config import settings
from app.core.email import send_email
from app.models.models import User


class SupportService:
    """Sends an in-app "contact support" message as an email to the support
    inbox — no ticket record kept in the app, this is a thin pass-through.
    """

    ALLOWED_ATTACHMENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def send_contact_message(
        self,
        current_user: User,
        *,
        subject: str,
        message: str,
        attachment_content: bytes | None = None,
        attachment_content_type: str | None = None,
        attachment_filename: str | None = None,
    ) -> None:
        attachment = None
        if attachment_content is not None:
            if attachment_content_type not in self.ALLOWED_ATTACHMENT_TYPES:
                raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="UNSUPPORTED_IMAGE_TYPE")
            if not attachment_content or len(attachment_content) > settings.CLINICAL_IMAGE_MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="IMAGE_TOO_LARGE")
            attachment = (attachment_content, attachment_filename or "anexo", attachment_content_type)

        body = (
            f"Nova mensagem de suporte pela plataforma.\n\n"
            f"De: {current_user.name} <{current_user.email}>\n"
            f"Papel: {', '.join(current_user.roles) or 'desconhecido'}\n"
            f"Assunto: {subject}\n\n"
            f"{message}\n"
        )

        sent = send_email(
            to=settings.SUPPORT_CONTACT_EMAIL,
            subject=f"[Suporte Julha] {subject}",
            body=body,
            attachment=attachment,
        )
        if not sent:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SUPPORT_EMAIL_DELIVERY_FAILED")
