import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.models import Symptom, User

logger = logging.getLogger(__name__)


def is_negative(message: str) -> bool:
    negatives = [
        "não",
        "nao",
        "nenhum",
        "nenhuma",
        "não tive",
        "nao tive",
        "sem sintomas"
    ]

    message = message.lower().strip()
    result = any(n in message for n in negatives)

    logger.info(
        "is_negative check",
        extra={
            "message": message,
            "result": result
        }
    )

    return result


class SymptomService:

    @staticmethod
    def process_daily_response(db: Session, user: User, message: str):

        logger.info(
            "Processing daily response",
            extra={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "awaiting": user.awaiting_daily_response,
                "last_prompt": user.last_daily_prompt_at,
                "message": message
            }
        )

        # 1️⃣ Não está aguardando resposta
        if not user.awaiting_daily_response:
            logger.warning(
                "User not awaiting daily response",
                extra={"user_id": user.id}
            )
            return "NOT_AWAITING"

        # 2️⃣ Timeout de 24h
        if user.last_daily_prompt_at:
            delta = datetime.now(timezone.utc) - user.last_daily_prompt_at

            logger.info(
                "Time delta check",
                extra={
                    "user_id": user.id,
                    "delta_hours": delta.total_seconds() / 3600
                }
            )

            if delta > timedelta(hours=24):
                logger.warning(
                    "Response expired (>24h)",
                    extra={"user_id": user.id}
                )
                user.awaiting_daily_response = False
                db.commit()
                return "EXPIRED"

        # 3️⃣ Resposta negativa
        if is_negative(message):
            logger.info(
                "Negative response detected",
                extra={"user_id": user.id}
            )
            user.awaiting_daily_response = False
            db.commit()
            return "NEGATIVE"

        # 4️⃣ Salvando sintoma
        symptom = Symptom(
            user_id=user.id,
            description=message
        )

        db.add(symptom)
        user.awaiting_daily_response = False
        db.commit()

        logger.info(
            "Symptom saved successfully",
            extra={
                "user_id": user.id,
                "symptom_id": symptom.id
            }
        )

        return "SAVED"
