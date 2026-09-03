from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from app.core.auth import get_current_user
from app.core.rate_limit import limiter
from app.models.models import User
from app.services.support_service import SupportService

router = APIRouter(tags=["Support"])


@router.post("/contact", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def send_support_contact(
    request: Request,
    subject: str = Form(..., min_length=1, max_length=120),
    message: str = Form(..., min_length=1, max_length=4000),
    attachment: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
):
    attachment_content = attachment.file.read() if attachment else None
    SupportService().send_contact_message(
        current_user,
        subject=subject,
        message=message,
        attachment_content=attachment_content,
        attachment_content_type=attachment.content_type if attachment else None,
        attachment_filename=attachment.filename if attachment else None,
    )
    return None
