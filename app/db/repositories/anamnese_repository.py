from sqlalchemy.orm import Session
from app.models.models import Anamnese

class AnamneseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_anamnese(self, user_id: int, info: str):
        anamnese = Anamnese(user_id=user_id, info=info)
        self.db.add(anamnese)
        self.db.commit()
        self.db.refresh(anamnese)
        return anamnese

    def get_anamneses_by_user(self, user_id: int):
        return self.db.query(Anamnese).filter(Anamnese.user_id == user_id).all()
