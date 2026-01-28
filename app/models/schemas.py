from pydantic import BaseModel, EmailStr
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from typing import List, Literal

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# ============================================================
#                       USER SCHEMAS
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
    # Aceita senha simples, será convertida para hashed_password no service
    password: Optional[str] = None
    is_admin: Optional[bool] = False


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    is_admin: bool

    class Config:
        from_attributes = True
        
class UserUpdate(UserBase):
    password: Optional[str] = None
    is_admin: Optional[bool] = None


# ============================================================
#                     ANAMNESE SCHEMAS
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
#                     SYMPTOM SCHEMAS
# ============================================================

class SymptomBase(BaseModel):
    description: str


class SymptomCreate(SymptomBase):
    pass


class SymptomRead(SymptomBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
#                    DAILY LOG SCHEMAS
# ============================================================

class DailyLogBase(BaseModel):
    action: str


class DailyLogCreate(DailyLogBase):
    pass


class DailyLogRead(DailyLogBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ============================================================
#                    INSIGHT SCHEMAS
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
    nivel_de_suspeicao: Literal["baixo", "moderado", "alto"]
    justificativa: List[str]

class InsightRequest(BaseModel):
    relatorio_texto: str


class InsightScenario(BaseModel):
    descricao: str
    condicoes_para_ocorrer: str
    probabilidade: Literal["baixa", "media", "alta"]


class InsightScenarios(BaseModel):
    otimista: InsightScenario
    intermediario: InsightScenario
    grave: InsightScenario


class InsightPreventiveResponse(BaseModel):
    cenarios: InsightScenarios
    cenario_mais_provavel: Literal["otimista", "intermediario", "grave"]
    especialista_recomendado: str
    exames_sugeridos: List[str]
    alerta_importante: str

class AvaliacaoClinica(BaseModel):
    hipotese_principal: str
    nivel_de_suspeicao: Literal["baixo", "moderado", "alto"]
    justificativa: List[str]


class InsightClinicalResponse(BaseModel):
    avaliacao_clinica: AvaliacaoClinica
    especialista_recomendado: str
    exames_prioritarios: List[str]
    urgencia: Literal["baixa", "media", "alta"]
    alerta_legal: str
