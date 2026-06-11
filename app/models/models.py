from sqlalchemy import (
    Column, Integer, String, Date, DateTime,
    ForeignKey, Text, Boolean, Enum, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.base_class import Base
import enum


# ============================================================
# ENUMS
# ============================================================

class CheckTypeEnum(str, enum.Enum):
    MORNING = "MORNING"
    NIGHT = "NIGHT"


class NivelSuspeicaoEnum(str, enum.Enum):
    BAIXO = "baixo"
    MODERADO = "moderado"
    ALTO = "alto"


class UrgenciaEnum(str, enum.Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


# ============================================================
# USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)

    telegram_id = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)

    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    cpf = Column(String, nullable=True, unique=True)

    hashed_password = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    current_report_id = Column(Integer, nullable=True)
    pending_check_type = Column(Enum(CheckTypeEnum), nullable=True)
    pending_report_date = Column(Date, nullable=True)
    pending_prompt_sent_at = Column(DateTime(timezone=True), nullable=True)

    # relationships
    anamnese = relationship("Anamnese", back_populates="user", uselist=False)

    daily_reports = relationship(
        "DailyReport",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="DailyReport.user_id"
    )

    current_report = relationship(
        "DailyReport",
        foreign_keys=[current_report_id],
        post_update=True
    )

    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# ============================================================
# ANAMNESE
# ============================================================

class Anamnese(Base):
    __tablename__ = "anamneses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    info = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="anamnese")


# ============================================================
# DAILY REPORT
# ============================================================

class DailyReport(Base):
    __tablename__ = "daily_reports"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "report_date",
            "check_type",
            name="uq_user_report_date_check"
        ),
        Index("ix_daily_reports_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    check_type = Column(Enum(CheckTypeEnum), nullable=False)

    symptom_description = Column(Text, nullable=True)
    suspected_cause = Column(Text, nullable=True)
    had_symptoms = Column(Boolean, nullable=False)
    completed = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship(
        "User",
        back_populates="daily_reports",
        foreign_keys=[user_id]
    )


# ============================================================
# REFRESH TOKEN
# ============================================================

class RefreshToken(Base):

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    token = Column(String, nullable=False, unique=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="refresh_tokens")


# ============================================================
# TELEGRAM LINK CODE
# ============================================================

class TelegramLinkCode(Base):

    __tablename__ = "telegram_link_codes"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    code = Column(String, nullable=False, unique=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)

    user = relationship("User")