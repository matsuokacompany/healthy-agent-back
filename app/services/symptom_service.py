from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.models import Symptom, User


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
    return any(n in message for n in negatives)


class SymptomService:

    @staticmethod
    def process_daily_response(db: Session, user: User, message: str):

        # Se não está aguardando resposta, ignora
        if not user.awaiting_daily_response:
            return

        # Segurança opcional: ignora resposta muito tardia
        if user.last_daily_prompt_at:
            if datetime.now(timezone.utc) - user.last_daily_prompt_at > timedelta(hours=24):
                user.awaiting_daily_response = False
                db.commit()
                return

        # Se resposta negativa → apenas encerra ciclo
        if is_negative(message):
            user.awaiting_daily_response = False
            db.commit()
            return

        # Caso contrário → salva sintoma
        symptom = Symptom(
            user_id=user.id,
            description=message
        )

        db.add(symptom)

        user.awaiting_daily_response = False

        db.commit()
