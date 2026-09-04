from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.dependencies import get_db
from app.models.models import User
from app.models.schemas import (
    CustomClinicalSummary,
    MonitoringPlanRead,
    SelfMonitoringInsightListResponse,
    SelfMonitoringInsightRead,
)
from app.services.self_monitoring_service import SelfMonitoringService

router = APIRouter(tags=["Self Monitoring"])


@router.post("/plan", response_model=MonitoringPlanRead, status_code=status.HTTP_201_CREATED)
def create_or_reactivate_self_monitoring_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).create_or_reactivate_plan(current_user)


@router.get("/evolution-report", response_model=CustomClinicalSummary)
def get_self_monitoring_evolution_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).evolution_report(
        current_user,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/insight", response_model=SelfMonitoringInsightRead)
def get_self_monitoring_insight(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).insight_report(
        current_user,
        api_key=settings.OPENAI_API_KEY,
        model_name=settings.AI_REPORT_MODEL,
        max_input_tokens=settings.AI_REPORT_MAX_INPUT_TOKENS,
        max_output_tokens=settings.AI_REPORT_MAX_OUTPUT_TOKENS,
        max_cost_usd=settings.AI_REPORT_MAX_COST_USD,
        input_cost_per_million_usd=settings.AI_REPORT_INPUT_COST_PER_MILLION_USD,
        output_cost_per_million_usd=settings.AI_REPORT_OUTPUT_COST_PER_MILLION_USD,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/insights", response_model=SelfMonitoringInsightListResponse)
def list_self_monitoring_insights(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).list_insights(current_user, page=page, per_page=per_page)


@router.get("/insights/{insight_id}", response_model=SelfMonitoringInsightRead)
def get_self_monitoring_insight_detail(
    insight_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfMonitoringService(db).get_insight(current_user, insight_id)
