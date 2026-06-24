import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class CheckTypeEnum(str, enum.Enum):
    MORNING = "MORNING"
    NIGHT = "NIGHT"


class DailyReportStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_CAUSE = "AWAITING_CAUSE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class NivelSuspeicaoEnum(str, enum.Enum):
    BAIXO = "baixo"
    MODERADO = "moderado"
    ALTO = "alto"


class UrgenciaEnum(str, enum.Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    telegram_id = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True, unique=True, index=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    cpf = Column(String, nullable=True, unique=True)
    hashed_password = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    anamnese = relationship("Anamnese", back_populates="user", cascade="all, delete-orphan", uselist=False)
    daily_reports = relationship("DailyReport", back_populates="user", cascade="all, delete-orphan")
    monitoring_plans = relationship(
        "MonitoringPlan",
        back_populates="patient",
        cascade="all, delete-orphan",
        foreign_keys="MonitoringPlan.patient_id",
    )
    professional_profile = relationship(
        "ProfessionalProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    telegram_link_codes = relationship("TelegramLinkCode", back_populates="user", cascade="all, delete-orphan")


class ProfessionalProfile(Base):
    __tablename__ = "professional_profiles"
    __table_args__ = (
        UniqueConstraint("license_number", "license_state", name="uq_professional_license"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    license_number = Column(String, nullable=True)
    license_state = Column(String, nullable=True)
    specialty = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="professional_profile")
    monitoring_links = relationship("MonitoringProfessional", back_populates="professional", cascade="all, delete-orphan")
    monitoring_plans = relationship(
        "MonitoringPlan",
        secondary="monitoring_professionals",
        back_populates="professionals",
        viewonly=True,
    )


class MonitoringPlan(Base):
    __tablename__ = "monitoring_plans"
    __table_args__ = (
        Index("ix_monitoring_plans_patient_id", "patient_id"),
        Index("ix_monitoring_plans_active_dates", "active", "start_date", "end_date"),
    )

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    patient = relationship("User", back_populates="monitoring_plans", foreign_keys=[patient_id])
    professional_links = relationship("MonitoringProfessional", back_populates="monitoring_plan", cascade="all, delete-orphan")
    professionals = relationship(
        "ProfessionalProfile",
        secondary="monitoring_professionals",
        back_populates="monitoring_plans",
        viewonly=True,
    )
    daily_reports = relationship("DailyReport", back_populates="monitoring_plan", cascade="all, delete-orphan")


class MonitoringProfessional(Base):
    __tablename__ = "monitoring_professionals"
    __table_args__ = (
        UniqueConstraint("monitoring_plan_id", "professional_profile_id", name="uq_monitoring_plan_professional"),
        Index("ix_monitoring_professionals_plan_id", "monitoring_plan_id"),
        Index("ix_monitoring_professionals_professional_id", "professional_profile_id"),
    )

    id = Column(Integer, primary_key=True)
    monitoring_plan_id = Column(Integer, ForeignKey("monitoring_plans.id"), nullable=False)
    professional_profile_id = Column(Integer, ForeignKey("professional_profiles.id"), nullable=False)
    role = Column(String, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    monitoring_plan = relationship("MonitoringPlan", back_populates="professional_links")
    professional = relationship("ProfessionalProfile", back_populates="monitoring_links")


class Anamnese(Base):
    __tablename__ = "anamneses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    info = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="anamnese")


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("monitoring_plan_id", "report_date", "check_type", name="uq_plan_report_date_check"),
        Index("ix_daily_reports_user_id", "user_id"),
        Index("ix_daily_reports_monitoring_plan_id", "monitoring_plan_id"),
        Index("ix_daily_reports_report_date", "report_date"),
        Index("ix_daily_reports_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    monitoring_plan_id = Column(Integer, ForeignKey("monitoring_plans.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    check_type = Column(Enum(CheckTypeEnum), nullable=False)
    status = Column(Enum(DailyReportStatusEnum), default=DailyReportStatusEnum.PENDING, nullable=False)
    symptom_description = Column(Text, nullable=True)
    suspected_cause = Column(Text, nullable=True)
    had_symptoms = Column(Boolean, nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    awaiting_response = Column(Boolean, default=True, nullable=False)
    awaiting_cause = Column(Boolean, default=False, nullable=False)
    prompt_sent_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="daily_reports")
    monitoring_plan = relationship("MonitoringPlan", back_populates="daily_reports")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="telegram_link_codes")
