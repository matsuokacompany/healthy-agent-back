import math

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import AiReportCache
from app.models.schemas import (
    CustomAiReportListItem,
    CustomAiReportListResponse,
    CustomAiReportResponse,
    PatientDashboardPagination,
)
from app.services.custom_report_generation_service import CustomReportGenerationService
from app.services.patient_dashboard_service import PaginationParams


class CustomReportHistoryService:
    def __init__(self, db: Session):
        self.db = db

    def list_reports(
        self,
        patient_id: int,
        *,
        pagination: PaginationParams,
        report_status: str | None = None,
    ) -> CustomAiReportListResponse:
        query = self._patient_reports_query(patient_id)
        if report_status:
            query = query.filter(AiReportCache.status == report_status)
        total = query.count()
        reports = (
            query.order_by(AiReportCache.requested_at.desc(), AiReportCache.id.desc())
            .offset(pagination.offset)
            .limit(pagination.per_page)
            .all()
        )
        return CustomAiReportListResponse(
            items=[self._list_item(report) for report in reports],
            pagination=PatientDashboardPagination(
                page=pagination.page,
                per_page=pagination.per_page,
                total=total,
                total_pages=math.ceil(total / pagination.per_page) if total else 0,
            ),
        )

    def get_report(self, patient_id: int, report_id: int) -> CustomAiReportResponse:
        report = self._patient_reports_query(patient_id).filter(AiReportCache.id == report_id).first()
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI report not found")
        return CustomReportGenerationService._response(report)

    def _patient_reports_query(self, patient_id: int):
        return self.db.query(AiReportCache).filter(
            AiReportCache.patient_id == patient_id,
            AiReportCache.periodo == "personalizado",
            AiReportCache.start_date.is_not(None),
            AiReportCache.end_date.is_not(None),
        )

    @staticmethod
    def _list_item(report: AiReportCache) -> CustomAiReportListItem:
        return CustomAiReportListItem(
            report_id=report.id,
            patient_id=report.patient_id,
            requested_by_user_id=report.professional_user_id,
            start_date=report.start_date,
            end_date=report.end_date,
            modo=report.modo,
            status=report.status,
            requested_at=report.requested_at,
            generated_at=report.generated_at,
            next_generation_at=report.next_generation_at,
            estimated_cost=float(report.estimated_cost) if report.estimated_cost is not None else None,
            actual_cost=float(report.actual_cost) if report.actual_cost is not None else None,
            model_name=report.model_name,
            failure_code=report.failure_code,
        )
