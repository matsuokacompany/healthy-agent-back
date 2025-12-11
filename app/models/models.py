from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base_class import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    cpf= Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)

    anamneses = relationship("Anamnese", back_populates="user")
    symptoms = relationship("Symptom", back_populates="user")
    daily_logs = relationship("DailyLog", back_populates="user")


class Anamnese(Base):
    __tablename__ = "anamneses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    info = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User", back_populates="anamneses")


class Symptom(Base):
    __tablename__ = "symptoms"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    description = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User", back_populates="symptoms")


class DailyLog(Base):
    __tablename__ = "daily_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User", back_populates="daily_logs")
