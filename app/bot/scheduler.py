from app.models.models import DailyReport, User, CheckTypeEnum
from app.db.session import SessionLocal
from datetime import datetime
import asyncio

async def send_prompt(bot_app, check_type: CheckTypeEnum):
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.telegram_id.isnot(None)).all()

        for user in users:
            # Cria relatório diário
            report = DailyReport(
                user_id=user.id,
                check_type=check_type
            )
            db.add(report)
            db.flush()  # Para gerar o ID antes do commit

            # Atualiza controle de fluxo do bot
            user.current_report_id = report.id

            # Mensagem dependendo do turno
            if check_type == CheckTypeEnum.MORNING:
                message = (
                    "🌅 Bom dia!\n"
                    "Você teve algum sintoma indesejado antes de dormir ou enquanto dormia?"
                )
            else:
                message = (
                    "🌙 Boa noite!\n"
                    "Você teve algum sintoma indesejado durante o dia?"
                )

            await bot_app.bot.send_message(
                chat_id=user.telegram_id,
                text=message
            )

        db.commit()
    finally:
        db.close()


async def schedule_prompts(bot_app):
    """
    Exemplo simples usando asyncio: envia prompts às 10h e 22h.
    """
    while True:
        now = datetime.now()
        hour = now.hour

        if hour == 10:
            await send_prompt(bot_app, CheckTypeEnum.MORNING)
        elif hour == 22:
            await send_prompt(bot_app, CheckTypeEnum.NIGHT)

        # Espera 60 segundos antes de checar novamente
        await asyncio.sleep(60)