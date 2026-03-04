from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import DailyReport, User
from app.models.schemas import DailyReportRead, DailyReportUpdate
from app.core.dependencies import get_db
from app.core.auth import get_current_user

router = APIRouter(tags=["Daily Reports"])


@router.get("/", response_model=list[DailyReportRead])
def get_my_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(DailyReport)
        .filter(DailyReport.user_id == current_user.id)
        .order_by(DailyReport.created_at.desc())
        .all()
    )


@router.get("/{report_id}", response_model=DailyReportRead)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = (
        db.query(DailyReport)
        .filter(
            DailyReport.id == report_id,
            DailyReport.user_id == current_user.id,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.patch("/{report_id}", response_model=DailyReportRead)
def update_report(
    report_id: int,
    data: DailyReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = (
        db.query(DailyReport)
        .filter(
            DailyReport.id == report_id,
            DailyReport.user_id == current_user.id,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(report, field, value)

    db.commit()
    db.refresh(report)
    return report