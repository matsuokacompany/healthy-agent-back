from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.models import User

class DailyReportRepository:
    """
    Repository para controlar fluxo de prompts diários do usuário.
    """

    def __init__(self, db: Session):
        self.db = db

    def mark_prompt_sent(self, user: User):
        """
        Marca que o usuário recebeu o prompt.
        """
        user.current_report_id = user.current_report_id or None
        self.db.commit()
        return user

    def mark_response_received(self, user: User):
        """
        Marca que o usuário respondeu.
        """
        user.current_report_id = None
        self.db.commit()
        return user

    def is_awaiting(self, user: User) -> bool:
        """
        Retorna True se o usuário está aguardando resposta.
        """
        return bool(user.current_report_id)