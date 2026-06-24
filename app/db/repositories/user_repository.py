from sqlalchemy.orm import Session

from app.models.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: int):
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_telegram_id(self, telegram_id: str):
        return self.db.query(User).filter(User.telegram_id == telegram_id).first()

    def create(self, telegram_id: str, name: str, email: str | None = None):
        safe_email = email or f"{telegram_id}@telegram.local"
        user = User(telegram_id=telegram_id, name=name, email=safe_email)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_or_create_by_telegram_id(self, telegram_id: str, name: str):
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            user = self.create(telegram_id=telegram_id, name=name)
        return user
