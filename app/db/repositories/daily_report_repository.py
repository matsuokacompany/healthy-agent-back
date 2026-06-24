from sqlalchemy.orm import Session

from app.models.models import DailyReport, DailyReportStatusEnum, User


class DailyReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_open_report_for_user(self, user: User) -> DailyReport | None:
        return (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == user.id)
            .filter(DailyReport.completed.is_(False))
            .filter(
                DailyReport.status.in_(
                    [
                        DailyReportStatusEnum.PENDING,
                        DailyReportStatusEnum.AWAITING_SYMPTOM_DESCRIPTION,
                        DailyReportStatusEnum.AWAITING_CAUSE,
                    ]
                )
            )
            .order_by(DailyReport.created_at.desc(), DailyReport.id.desc())
            .first()
        )

    def is_awaiting(self, user: User) -> bool:
        return self.get_open_report_for_user(user) is not None
