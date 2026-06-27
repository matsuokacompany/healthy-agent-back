from pydantic import BaseModel, EmailStr, Field
from datetime import date, datetime
from typing import Optional, List, Literal
from enum import Enum

# ============================================================
# ENUMS
# ============================================================

class CheckTypeEnum(str, Enum):
    MORNING = "MORNING"
    NIGHT = "NIGHT"


class NivelSuspeicaoEnum(str, Enum):
    BAIXO = "baixo"
    MODERADO = "moderado"
    ALTO = "alto"


class UrgenciaEnum(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


# ============================================================
# USER SCHEMAS
# ============================================================

class UserBase(BaseModel):
    name: str
    email: EmailStr
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    cpf: Optional[str] = None


class UserCreate(UserBase):
    password: Optional[str] = None
    is_admin: Optional[bool] = False
    role: Optional[Literal["patient", "professional", "super_admin"]] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    cpf: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    role: Optional[Literal["patient", "professional", "super_admin"]] = None


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    is_admin: bool
    role: Literal["patient", "professional", "super_admin"]

    class Config:
        from_attributes = True



class AuthUserPayload(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Literal["patient", "professional", "super_admin"]
    active_context: Optional[Literal["admin", "professional", "patient"]] = None
    active_context_label: Optional[str] = None


class AuthLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    redirect_to: str
    user: AuthUserPayload


class ChooseContextRequest(BaseModel):
    context: Literal["admin", "professional", "patient"]


class ChooseContextResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    redirect_to: str
    user: AuthUserPayload

# ============================================================
# ANAMNESE SCHEMAS
# ============================================================

class AnamneseBase(BaseModel):
    info: str


class AnamneseCreate(AnamneseBase):
    user_id: int


class AnamneseUpdate(BaseModel):
    info: Optional[str] = None


class AnamneseRead(AnamneseBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# DAILY REPORT SCHEMAS
# ============================================================

class DailyReportBase(BaseModel):
    check_type: CheckTypeEnum
    symptom_description: Optional[str] = Field(None, max_length=280)
    suspected_cause: Optional[str] = Field(None, max_length=280)


class DailyReportCreate(BaseModel):
    check_type: CheckTypeEnum


class DailyReportUpdate(BaseModel):
    symptom_description: Optional[str] = Field(None, max_length=280)
    suspected_cause: Optional[str] = Field(None, max_length=280)
    completed: Optional[bool] = None


class DailyReportRead(DailyReportBase):
    id: int
    user_id: int
    completed: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# INSIGHT SCHEMAS
# ============================================================

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


# ============================================================
# REFRESH TOKEN
# ============================================================

class RefreshTokenRequest(BaseModel):
    refresh_token: str