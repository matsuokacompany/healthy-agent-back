from pydantic import BaseModel, EmailStr
from datetime import date, datetime
from typing import Optional

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

    class Config:
        from_attributes = True


# ============================================================
#                     SYMPTOM SCHEMAS
# ============================================================

class SymptomBase(BaseModel):
    description: str


class SymptomCreate(SymptomBase):
    user_id: int


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
    user_id: int


class DailyLogRead(DailyLogBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
