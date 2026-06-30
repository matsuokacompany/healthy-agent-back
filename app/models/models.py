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
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class CheckTypeEnum(str, enum.Enum):
    MORNING = "MORNING"
    NIGHT = "NIGHT"


class DailyReportStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_SYMPTOM_DESCRIPTION = "AWAITING_SYMPTOM_DESCRIPTION"
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


class RoleNameEnum(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PROFESSIONAL = "professional"
    PATIENT = "patient"


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("ix_user_roles_user_id", "user_id"),
        Index("ix_user_roles_role_id", "role_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="role_links")
    role = relationship("Role", back_populates="user_links")


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user_links = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    users = relationship("User", secondary="user_roles", back_populates="role_records", viewonly=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    supabase_user_id = Column(UUID(as_uuid=True), nullable=True, unique=True, index=True)
    phone = Column(String, nullable=True, unique=True, index=True)
    whatsapp_wa_id = Column(String, nullable=True, unique=True, index=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    cpf = Column(String, nullable=True, unique=True)
    is_admin = Column(Boolean, default=False, nullable=False)  # Deprecated: use roles/user_roles for authorization.
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
    role_links = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    role_records = relationship("Role", secondary="user_roles", back_populates="users", viewonly=True)

    @property
    def roles(self) -> list[str]:
        return [role.name for role in self.role_records]


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_whatsapp_messages_message_id"),
        Index("ix_whatsapp_messages_user_id", "user_id"),
        Index("ix_whatsapp_messages_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    message_id = Column(String, nullable=False)
    channel = Column(String, nullable=False, default="whatsapp")
    external_user_id = Column(String, nullable=False)
    normalized_user_id = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, default="PROCESSING")
    response_text = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")


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
