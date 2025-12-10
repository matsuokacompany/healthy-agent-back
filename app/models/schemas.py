from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional

# ---------- USER ----------
class UserBase(BaseModel):
    name: str
    email: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True

# ---------- ANAMNESE ----------
class AnamneseBase(BaseModel):
    info: str

class AnamneseCreate(AnamneseBase):
    user_id: int

class AnamneseRead(AnamneseBase):
    id: int
    user_id: int
    created_at: datetime
    class Config:
        orm_mode = True

# ---------- SYMPTOM ----------
class SymptomBase(BaseModel):
    description: str

class SymptomCreate(SymptomBase):
    user_id: int

class SymptomRead(SymptomBase):
    id: int
    user_id: int
    created_at: datetime
    class Config:
        orm_mode = True

# ---------- DAILY LOG ----------
class DailyLogBase(BaseModel):
    action: str

class DailyLogCreate(DailyLogBase):
    user_id: int

class DailyLogRead(DailyLogBase):
    id: int
    user_id: int
    created_at: datetime
    class Config:
        orm_mode = True
