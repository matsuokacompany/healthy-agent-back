from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import SessionLocal
from app.db.repositories.user_repository import UserRepository
from app.services.report_service import ReportService

async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE, periodo: str):
    telegram_id = str(update.message.from_user.id)
    with SessionLocal() as db:
        user_repo = UserRepository(db)
        user = user_repo.get_user_by_telegram_id(telegram_id)
        if not user:
            await update.message.reply_text("Você ainda não possui registros suficientes.")
            return

        service = ReportService(db)
        texto = service.gerar_relatorio(user.id, periodo)
        await update.message.reply_text(texto)

async def relatorio_semanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await relatorio(update, context, "semanal")

async def relatorio_mensal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await relatorio(update, context, "mensal")
