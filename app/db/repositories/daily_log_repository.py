from sqlalchemy.orm import Session
from app.models.models import DailyLog

class DailyLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_log(self, user_id: int, action: str):
        log = DailyLog(user_id=user_id, action=action)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_logs_by_user(self, user_id: int):
        return self.db.query(DailyLog).filter(DailyLog.user_id == user_id).all()
