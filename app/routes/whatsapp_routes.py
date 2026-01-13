from fastapi import APIRouter, Request
from app.db.session import SessionLocal
from app.services.daily_log_service import save_daily_response

router = APIRouter()

@router.post("/bot/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    form = await request.form()

    message = form.get("Body")
    from_number = form.get("From")  # whatsapp:+55...

    db = SessionLocal()
    try:
        save_daily_response(
            db=db,
            phone_or_telegram_id=from_number,
            message=message
        )
    finally:
        db.close()

    return {"status": "ok"}
