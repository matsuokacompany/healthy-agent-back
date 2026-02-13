from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram import Update

from app.db.session import SessionLocal
from app.models.models import User
from app.services.symptom_service import SymptomService


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    db = SessionLocal()

    telegram_id = str(update.message.from_user.id)

    user = db.query(User).filter(
        User.telegram_id == telegram_id
    ).first()

    if not user:
        user = User(
            name=update.message.from_user.full_name,
            telegram_id=telegram_id
        )
        db.add(user)
        db.commit()

    SymptomService.process_daily_response(
        db=db,
        user=user,
        message=update.message.text
    )

    db.close()


def start_bot(token: str):
    app = ApplicationBuilder().token(token).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    return app
