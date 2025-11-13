from sqlalchemy.orm import Session
from app.models.models import Symptom
from datetime import datetime


class SymptomRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, description: str):
        symptom = Symptom(user_id=user_id, description=description)
        self.db.add(symptom)
        self.db.commit()
        self.db.refresh(symptom)
        return symptom

    def get_symptoms_by_user(self, user_id: int):
        return self.db.query(Symptom).filter(Symptom.user_id == user_id).all()

    def list_by_user(self, user_id: int):
        return self.db.query(Symptom).filter(Symptom.user_id == user_id).all()

    def get_last_for_user(self, user_id: int):
        return (
            self.db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .order_by(Symptom.id.desc())
            .first()
        )

    def listar_por_periodo(self, user_id: int, inicio: datetime, fim: datetime):
        return (
            self.db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .filter(Symptom.date >= inicio)
            .filter(Symptom.date <= fim)
            .all()
        )
