from datetime import date, datetime
from enum import Enum
from uuid import UUID
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

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
