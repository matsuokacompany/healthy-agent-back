from datetime import date, datetime
from enum import Enum
from uuid import UUID
from typing import ClassVar, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.user_identity import validate_user_name


class CheckTypeEnum(str, Enum):
    MORNING = "MORNING"
    NIGHT = "NIGHT"


class DailyReportStatusEnum(str, Enum):
    PENDING = "PENDING"
    AWAITING_SYMPTOM_DESCRIPTION = "AWAITING_SYMPTOM_DESCRIPTION"
    AWAITING_CAUSE = "AWAITING_CAUSE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class NivelSuspeicaoEnum(str, Enum):
    BAIXO = "baixo"
    MODERADO = "moderado"
    ALTO = "alto"


class UrgenciaEnum(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class AiReportStatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RoleNameEnum(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PROFESSIONAL = "professional"
    PATIENT = "patient"


class ORMModel(BaseModel):
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    cpf: Optional[str] = None


class UserCreate(UserBase):
    supabase_user_id: Optional[str] = None
    roles: List[RoleNameEnum] = Field(default_factory=lambda: [RoleNameEnum.PATIENT])

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_user_name(value)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return validate_user_name(value)

    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    cpf: Optional[str] = None


class UserRead(UserBase, ORMModel):
    id: int
    supabase_user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    roles: List[RoleNameEnum] = Field(default_factory=list)


class UserRoleUpdate(BaseModel):
    roles: List[RoleNameEnum]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=1024)


class AnamneseBase(BaseModel):
    info: str


class AnamneseCreate(AnamneseBase):
    user_id: int


class AnamneseUpdate(BaseModel):
    info: Optional[str] = None


class AnamneseRead(AnamneseBase, ORMModel):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class ProfessionalProfileBase(BaseModel):
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    specialty: Optional[str] = None
    bio: Optional[str] = None
    active: bool = True


class ProfessionalProfileCreate(ProfessionalProfileBase):
    user_id: int


class ProfessionalProfileUpdate(BaseModel):
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    specialty: Optional[str] = None
    bio: Optional[str] = None
    active: Optional[bool] = None


class ProfessionalProfileRead(ProfessionalProfileBase, ORMModel):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class MonitoringPlanBase(BaseModel):
    title: str
    description: Optional[str] = None
    active: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class MonitoringPlanCreate(MonitoringPlanBase):
    patient_id: int


class MonitoringPlanUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class MonitoringPlanRead(MonitoringPlanBase, ORMModel):
    id: int
    patient_id: int
    created_at: datetime
    updated_at: datetime


class ProfessionalPatientCreate(UserBase):
    """Patient and initial monitoring plan created by a professional."""

    plan_title: str = Field(min_length=1, max_length=255)
    plan_description: Optional[str] = None
    plan_start_date: Optional[date] = None
    plan_end_date: Optional[date] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_user_name(value)


class ProfessionalPatientCreateResponse(BaseModel):
    patient: UserRead
    monitoring_plan: MonitoringPlanRead


class MonitoringProfessionalCreate(BaseModel):
    professional_profile_id: int
    role: Optional[str] = None


class MonitoringProfessionalUpdate(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None


class MonitoringProfessionalRead(ORMModel):
    id: int
    monitoring_plan_id: int
    professional_profile_id: int
    role: Optional[str] = None
    active: bool
    created_at: datetime


class DailyReportBase(BaseModel):
    check_type: CheckTypeEnum
    symptom_description: Optional[str] = Field(None, max_length=280)
    suspected_cause: Optional[str] = Field(None, max_length=280)


class DailyReportCreate(BaseModel):
    monitoring_plan_id: int
    check_type: CheckTypeEnum


class DailyReportUpdate(BaseModel):
    had_symptoms: Optional[bool] = None
    symptom_description: Optional[str] = Field(None, max_length=280)
    suspected_cause: Optional[str] = Field(None, max_length=280)

    class Config:
        extra = "forbid"


class DailyReportRead(DailyReportBase, ORMModel):
    id: int
    user_id: int
    monitoring_plan_id: int
    report_date: date
    had_symptoms: Optional[bool] = None
    status: DailyReportStatusEnum
    awaiting_response: bool
    awaiting_cause: bool
    prompt_sent_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class InsightScenario(BaseModel):
    descricao: str
    condicoes_para_ocorrer: str
    probabilidade: Literal["baixa", "media", "alta"]


class InsightScenarios(BaseModel):
    otimista: InsightScenario
    intermediario: InsightScenario
    grave: InsightScenario


class AvaliacaoClinica(BaseModel):
    hipotese_principal: str
    possiveis_doencas: List[str] = Field(default_factory=list)
    nivel_de_suspeicao: NivelSuspeicaoEnum
    justificativa: List[str]


class InsightRequest(BaseModel):
    relatorio_texto: str


class InsightPreventiveResponse(BaseModel):
    cenarios: InsightScenarios
    cenario_mais_provavel: Literal["otimista", "intermediario", "grave"]
    especialista_recomendado: str
    exames_sugeridos: List[str]
    alerta_importante: str


class InsightClinicalResponse(BaseModel):
    avaliacao_clinica: AvaliacaoClinica
    especialista_recomendado: str
    exames_prioritarios: List[str]
    urgencia: UrgenciaEnum
    alerta_legal: str


class PatientDashboardUser(BaseModel):
    id: int
    name: str
    first_name: str
    avatar: Optional[str] = None


class PatientMonitoringSummary(BaseModel):
    id: Optional[int] = None
    active: bool
    title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days_active: Optional[int] = None
    days_remaining: Optional[int] = None


class PatientDashboardToday(BaseModel):
    has_checkin: bool
    completed: bool = False
    status: Optional[DailyReportStatusEnum] = None
    prompt_sent_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None


class PatientDashboardStatistics(BaseModel):
    total: int
    answered: int
    missed: int
    with_symptoms: int
    without_symptoms: int
    adherence: float

    @classmethod
    def empty(cls) -> "PatientDashboardStatistics":
        return cls(
            total=0,
            answered=0,
            missed=0,
            with_symptoms=0,
            without_symptoms=0,
            adherence=0.0,
        )


class PatientLastResponse(BaseModel):
    date: date
    status: DailyReportStatusEnum
    had_symptoms: Optional[bool] = None


class PatientNextCheckin(BaseModel):
    scheduled_at: datetime


class PatientResponsibleProfessional(BaseModel):
    id: int
    name: str
    specialty: Optional[str] = None


class PatientAnamnesisSummary(BaseModel):
    has_anamnesis: bool
    conditions_count: Optional[int] = None
    preview: Optional[List[str]] = None


class PatientDashboardResponse(BaseModel):
    user: PatientDashboardUser
    monitoring: PatientMonitoringSummary
    today: PatientDashboardToday
    statistics: PatientDashboardStatistics
    last_response: Optional[PatientLastResponse] = None
    next_checkin: Optional[PatientNextCheckin] = None
    professionals: List[PatientResponsibleProfessional] = Field(default_factory=list)
    anamnesis_summary: PatientAnamnesisSummary


class PatientDashboardAlert(BaseModel):
    type: str
    severity: Literal["info", "warning", "critical"]
    message: str


class PatientDashboardResponseV2(BaseModel):
    user: PatientDashboardUser
    monitoring: PatientMonitoringSummary
    today: PatientDashboardToday
    next_checkin: Optional[PatientNextCheckin] = None
    anamnesis_summary: PatientAnamnesisSummary
    statistics: PatientDashboardStatistics
    last_response: Optional[PatientLastResponse] = None
    professionals: List[PatientResponsibleProfessional] = Field(default_factory=list)
    alerts: List[PatientDashboardAlert] = Field(default_factory=list)


class PatientDashboardPagination(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class PatientDashboardReportItem(BaseModel):
    id: int
    monitoring_plan_id: int
    report_date: date
    check_type: CheckTypeEnum
    status: DailyReportStatusEnum
    completed: bool
    had_symptoms: Optional[bool] = None
    symptom_description: Optional[str] = None
    suspected_cause: Optional[str] = None
    prompt_sent_at: datetime
    answered_at: Optional[datetime] = None
    expires_at: datetime


class PatientDashboardHistoryResponse(BaseModel):
    items: List[PatientDashboardReportItem]
    pagination: PatientDashboardPagination


class PatientDashboardCalendarCheckin(BaseModel):
    id: int
    check_type: CheckTypeEnum
    status: DailyReportStatusEnum
    completed: bool
    had_symptoms: Optional[bool] = None
    prompt_sent_at: datetime
    answered_at: Optional[datetime] = None


class PatientDashboardCalendarDay(BaseModel):
    date: date
    has_checkin: bool
    completed: bool
    pending: bool
    has_symptoms: bool
    statuses: List[DailyReportStatusEnum] = Field(default_factory=list)
    checkins: List[PatientDashboardCalendarCheckin] = Field(default_factory=list)


class PatientDashboardCalendarResponse(BaseModel):
    year: int
    month: int
    days: List[PatientDashboardCalendarDay]


class PatientDashboardStatisticsResponse(BaseModel):
    period: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    statistics: PatientDashboardStatistics


class PatientDashboardCheckinsResponse(BaseModel):
    items: List[PatientDashboardReportItem]
    pagination: PatientDashboardPagination


class ProfessionalPatientRead(BaseModel):
    patient_id: int
    name: str
    email: EmailStr
    phone: Optional[str] = None
    monitoring_plan_id: int
    plan_title: str
    active: bool
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_checkin_at: Optional[datetime] = None
    last_status: Optional[DailyReportStatusEnum] = None
    symptom_reports_count: int = 0


class ProfessionalAiReportRequest(BaseModel):
    periodo: Literal["diario", "semanal", "mensal"] = "semanal"
    modo: Literal["preventivo", "avaliacao_clinica"] = "avaliacao_clinica"


class ProfessionalAiReportResponse(BaseModel):
    patient_id: int
    periodo: Literal["diario", "semanal", "mensal"]
    modo: Literal["preventivo", "avaliacao_clinica"]
    clinical_summary: str
    ai: dict


class CustomAiReportPeriod(BaseModel):
    MIN_PERIOD_DAYS: ClassVar[int] = 30
    MAX_PERIOD_YEARS: ClassVar[int] = 5

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        if self.end_date > date.today():
            raise ValueError("end_date cannot be in the future")

        period_days = (self.end_date - self.start_date).days + 1
        if period_days < self.MIN_PERIOD_DAYS:
            raise ValueError(f"period must include at least {self.MIN_PERIOD_DAYS} days")

        try:
            maximum_end_date = self.start_date.replace(year=self.start_date.year + self.MAX_PERIOD_YEARS)
        except ValueError:
            maximum_end_date = self.start_date.replace(
                year=self.start_date.year + self.MAX_PERIOD_YEARS,
                day=28,
            )
        if self.end_date > maximum_end_date:
            raise ValueError(f"period cannot exceed {self.MAX_PERIOD_YEARS} calendar years")
        return self


class CustomAiReportPreviewRequest(CustomAiReportPeriod):
    modo: Literal["preventivo", "avaliacao_clinica"] = "avaliacao_clinica"


class CustomAiReportCreateRequest(CustomAiReportPreviewRequest):
    preview_token: str = Field(min_length=1)


class AiReportCooldownReleaseRequest(BaseModel):
    modo: Literal["preventivo", "avaliacao_clinica"]


class AiReportCooldownReleaseResponse(BaseModel):
    patient_id: int
    report_id: int
    modo: Literal["preventivo", "avaliacao_clinica"]
    released_by_user_id: int
    previous_next_generation_at: datetime
    released_at: datetime


class CustomAiReportEligibility(BaseModel):
    can_generate: bool
    reason: Optional[str] = None
    next_generation_at: Optional[datetime] = None
    sufficient_data: bool
    completed_checkins: int = Field(ge=0)
    minimum_required: int = Field(default=10, ge=1)
    latest_report_id: Optional[int] = None
    last_generated_at: Optional[datetime] = None


class CustomClinicalPeriodMetrics(BaseModel):
    total_checkins: int = Field(ge=0)
    completed_checkins: int = Field(ge=0)
    pending_checkins: int = Field(ge=0)
    checkins_with_symptoms: int = Field(ge=0)
    checkins_without_symptoms: int = Field(ge=0)
    days_with_checkins: int = Field(ge=0)
    adherence_percentage: float = Field(ge=0, le=100)
    symptom_rate_percentage: float = Field(ge=0, le=100)
    calendar_coverage_percentage: float = Field(ge=0, le=100)


class CustomClinicalSymptomOccurrence(BaseModel):
    description: str
    occurrences: int = Field(ge=1)
    first_reported_at: date
    last_reported_at: date


class CustomClinicalTimelineGroup(BaseModel):
    start_date: date
    end_date: date
    metrics: CustomClinicalPeriodMetrics


class CustomClinicalSummary(BaseModel):
    patient_id: int
    start_date: date
    end_date: date
    period_days: int = Field(ge=1)
    aggregation: Literal["weekly", "monthly", "yearly"]
    minimum_completed_checkins: int = Field(default=10, ge=1)
    sufficient_data: bool
    metrics: CustomClinicalPeriodMetrics
    symptom_trend: Literal["increasing", "decreasing", "stable", "insufficient_data"]
    longest_gap_days: int = Field(ge=0)
    symptoms: List[CustomClinicalSymptomOccurrence] = Field(default_factory=list)
    timeline: List[CustomClinicalTimelineGroup] = Field(default_factory=list)


class CustomAiReportPreviewResponse(BaseModel):
    modo: Literal["preventivo", "avaliacao_clinica"]
    eligibility: CustomAiReportEligibility
    summary: CustomClinicalSummary
    preview_token: Optional[str] = None
    preview_expires_at: Optional[datetime] = None


class CustomAiReportResponse(BaseModel):
    report_id: int
    patient_id: int
    start_date: date
    end_date: date
    modo: Literal["preventivo", "avaliacao_clinica"]
    status: AiReportStatusEnum
    requested_by_user_id: int
    requested_at: datetime
    processing_started_at: Optional[datetime] = None
    generated_at: Optional[datetime] = None
    next_generation_at: Optional[datetime] = None
    clinical_summary: Optional[str] = None
    ai: Optional[dict] = None
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    estimated_cost: Optional[float] = Field(default=None, ge=0)
    actual_cost: Optional[float] = Field(default=None, ge=0)
    model_name: Optional[str] = None
    failure_code: Optional[str] = None


class CustomAiReportListItem(BaseModel):
    report_id: int
    patient_id: int
    requested_by_user_id: int
    start_date: date
    end_date: date
    modo: Literal["preventivo", "avaliacao_clinica"]
    status: AiReportStatusEnum
    requested_at: datetime
    generated_at: Optional[datetime] = None
    next_generation_at: Optional[datetime] = None
    estimated_cost: Optional[float] = Field(default=None, ge=0)
    actual_cost: Optional[float] = Field(default=None, ge=0)
    model_name: Optional[str] = None
    failure_code: Optional[str] = None


class CustomAiReportListResponse(BaseModel):
    items: List[CustomAiReportListItem]
    pagination: PatientDashboardPagination
