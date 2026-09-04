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
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class CheckTypeEnum(str, enum.Enum):
    MORNING = "MORNING"
    NIGHT = "NIGHT"


class DailyReportStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_SYMPTOM_DESCRIPTION = "AWAITING_SYMPTOM_DESCRIPTION"
    AWAITING_CAUSE = "AWAITING_CAUSE"
    AWAITING_DIET_ADHERENCE = "AWAITING_DIET_ADHERENCE"
    AWAITING_DIET_DEVIATION_DESCRIPTION = "AWAITING_DIET_DEVIATION_DESCRIPTION"
    AWAITING_MEDICATION_ADHERENCE = "AWAITING_MEDICATION_ADHERENCE"
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


class AiReportStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ClinicalAttachmentStatusEnum(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    DELETED = "DELETED"


class ClinicalAttachmentSourceEnum(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    PATIENT_PORTAL = "PATIENT_PORTAL"
    PROFESSIONAL_PORTAL = "PROFESSIONAL_PORTAL"


class MonitoringPlanOriginEnum(str, enum.Enum):
    PROFESSIONAL = "PROFESSIONAL"
    SELF_SERVICE = "SELF_SERVICE"


class SubscriptionStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"


class PatientLinkRequestStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


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
    supabase_user_id = Column(Uuid(as_uuid=True), nullable=True, unique=True, index=True)
    phone = Column(String, nullable=True, unique=True, index=True)
    whatsapp_wa_id = Column(String, nullable=True, unique=True, index=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    cpf = Column(String, nullable=True, unique=True)
    # Only set by the self-service signup flow (POST /api/auth/signup).
    # Professional-provisioned patients have no direct acceptance to record,
    # since a professional is the one interacting with the platform on the
    # patient's behalf, so this stays NULL for them by design.
    terms_accepted_at = Column(DateTime(timezone=True), nullable=True)
    terms_version = Column(String, nullable=True)
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
    clinical_attachments = relationship(
        "ClinicalAttachment",
        back_populates="patient",
        cascade="all, delete-orphan",
        foreign_keys="ClinicalAttachment.patient_id",
    )
    subscription = relationship("Subscription", back_populates="user", cascade="all, delete-orphan", uselist=False)

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
    # Grandfathering + grace period for professional billing. Existing
    # profiles (as of the professional-billing rollout) are backfilled to a
    # fixed date; new self-signups get NULL (no grace — access depends on
    # their Subscription from day one). See payment_service.professional_has_access.
    free_until = Column(Date, nullable=True)
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
    origin = Column(String, nullable=False, default=MonitoringPlanOriginEnum.PROFESSIONAL.value)
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
    # Granted when this link is created by a patient accepting a
    # PatientLinkRequest while they still have a paying self-service
    # subscription — lets the professional bypass the monthly AI report
    # cooldown for this patient that many times, instead of the platform
    # cancelling the patient's subscription outright.
    bonus_report_credits = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    monitoring_plan = relationship("MonitoringPlan", back_populates="professional_links")
    professional = relationship("ProfessionalProfile", back_populates="monitoring_links")


class Anamnese(Base):
    __tablename__ = "anamneses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    info = Column(Text, nullable=True)
    info_encryption_envelope = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="anamnese")


class Supplement(Base):
    """A patient-managed list of supplements/medications they take — shown
    on the anamnese page, and read by the self-service WhatsApp check-in
    (DailyReportService) to name them in the medication-adherence question
    instead of asking a generic "took your meds?". Self-managed by the
    patient directly, unlike Anamnese.info which is professional-authored;
    see anamnese_routes.py's _require_clinical_write_access comment."""

    __tablename__ = "supplements"
    __table_args__ = (
        Index("ix_supplements_patient_id", "patient_id"),
    )

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


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
    symptom_description_encryption_envelope = Column(JSON, nullable=True)
    suspected_cause = Column(Text, nullable=True)
    suspected_cause_encryption_envelope = Column(JSON, nullable=True)
    had_symptoms = Column(Boolean, nullable=True)
    # Only asked for self-service (no professional) monitoring plans, as two
    # extra WhatsApp interactive-button questions in the same daily
    # conversation — see MonitoringPlanOriginEnum.SELF_SERVICE and
    # DailyReportService (AWAITING_DIET_ADHERENCE ->
    # [AWAITING_DIET_DEVIATION_DESCRIPTION] -> AWAITING_MEDICATION_ADHERENCE).
    # Both booleans are set directly from the button tap, deterministically —
    # no AI involved. lifestyle_notes only holds the patient's free-text
    # answer to "o que você comeu fora da dieta?", asked when diet_adherence
    # is False.
    diet_adherence = Column(Boolean, nullable=True)
    medication_adherence = Column(Boolean, nullable=True)
    lifestyle_notes = Column(Text, nullable=True)
    lifestyle_notes_encryption_envelope = Column(JSON, nullable=True)
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
    clinical_attachments = relationship("ClinicalAttachment", back_populates="daily_report")


class SymptomTerm(Base):
    """Controlled clinical vocabulary a free-text symptom_description gets
    normalized into (see SymptomNormalizationService) — shared across every
    patient, grown by the classifier only when nothing existing fits."""

    __tablename__ = "symptom_terms"

    id = Column(Integer, primary_key=True)
    label = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class DailyReportSymptomTerm(Base):
    """One row per (report, term) — a single check-in's description can
    normalize to more than one term (e.g. "Refluxo, dor de cabeça")."""

    __tablename__ = "daily_report_symptom_terms"
    __table_args__ = (
        Index("ix_daily_report_symptom_terms_patient", "patient_id"),
        Index("ix_daily_report_symptom_terms_term", "symptom_term_id"),
    )

    daily_report_id = Column(Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), primary_key=True)
    symptom_term_id = Column(Integer, ForeignKey("symptom_terms.id", ondelete="CASCADE"), primary_key=True)
    # Denormalized from daily_reports.user_id so RLS can check patient
    # access directly, matching ClinicalAttachment's pattern.
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class ClinicalAttachment(Base):
    __tablename__ = "clinical_attachments"
    __table_args__ = (
        Index("ix_clinical_attachments_patient_created", "patient_id", "created_at"),
        Index("ix_clinical_attachments_uploader", "uploaded_by_user_id"),
        Index(
            "uq_clinical_attachments_whatsapp_report",
            "daily_report_id",
            unique=True,
            postgresql_where=text("source = 'WHATSAPP' AND deleted_at IS NULL"),
            sqlite_where=text("source = 'WHATSAPP' AND deleted_at IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    monitoring_plan_id = Column(Integer, ForeignKey("monitoring_plans.id"), nullable=True)
    daily_report_id = Column(Integer, ForeignKey("daily_reports.id"), nullable=True)
    source = Column(String, nullable=False)
    whatsapp_message_id = Column(String, nullable=True, unique=True)
    whatsapp_media_id = Column(String, nullable=True, unique=True)
    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False, unique=True)
    content_type = Column(String, nullable=False, default="image/jpeg")
    byte_size = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    description = Column(String(500), nullable=True)
    status = Column(String, nullable=False, default=ClinicalAttachmentStatusEnum.AVAILABLE.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    patient = relationship("User", foreign_keys=[patient_id], back_populates="clinical_attachments")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])
    monitoring_plan = relationship("MonitoringPlan")
    daily_report = relationship("DailyReport", back_populates="clinical_attachments")


class AiReportCache(Base):
    __tablename__ = "ai_report_cache"
    __table_args__ = (
        Index("ix_ai_report_cache_patient_created", "patient_id", "created_at"),
        Index("ix_ai_report_cache_professional_created", "professional_user_id", "created_at"),
        Index("ix_ai_report_cache_patient_status_generated", "patient_id", "status", "generated_at"),
        Index("ix_ai_report_cache_patient_dates", "patient_id", "start_date", "end_date"),
        Index("ix_ai_report_cache_idempotency_key", "idempotency_key", unique=True),
        Index(
            "uq_ai_report_cache_patient_active",
            "patient_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'PROCESSING')"),
            sqlite_where=text("status IN ('PENDING', 'PROCESSING')"),
        ),
    )

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    professional_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    periodo = Column(String, nullable=False)
    modo = Column(String, nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default=AiReportStatusEnum.COMPLETED.value)
    clinical_summary_hash = Column(String, nullable=True)
    clinical_summary = Column(Text, nullable=True)
    clinical_summary_encryption_envelope = Column(JSON, nullable=True)
    # Persist Python None as SQL NULL so ciphertext-only writes and cleanup can
    # be audited with IS NULL instead of leaving a JSON `null` value behind.
    ai_response = Column(JSON(none_as_null=True), nullable=True)
    ai_response_encryption_envelope = Column(JSON, nullable=True)
    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    next_generation_at = Column(DateTime(timezone=True), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Numeric(12, 8), nullable=True)
    actual_cost = Column(Numeric(12, 8), nullable=True)
    model_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    failure_code = Column(String, nullable=True)
    failure_message = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    patient = relationship("User", foreign_keys=[patient_id])
    professional_user = relationship("User", foreign_keys=[professional_user_id])


class SelfMonitoringInsight(Base):
    """AI-generated evolution summary for a self-service (self_made) patient.

    One row per generation (history, not upserted) — deliberately kept
    separate from `ai_report_cache` because that table's RLS policy only
    allows service/admin/professional reads; a self-service patient has no
    professional and needs to read their own rows directly. Query the most
    recent row per patient_id (order by generated_at desc) for "the current
    summary"; see SelfMonitoringService for the cooldown logic that decides
    whether to reuse the latest row or insert a new one.
    """

    __tablename__ = "self_monitoring_insights"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    insight_response = Column(JSON(none_as_null=True), nullable=True)
    insight_response_encryption_envelope = Column(JSON, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Numeric(12, 8), nullable=True)
    actual_cost = Column(Numeric(12, 8), nullable=True)
    model_name = Column(String, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    next_generation_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    patient = relationship("User", foreign_keys=[patient_id])


class Subscription(Base):
    """A self-service (B2C) patient's paid subscription to the monitoring plan.

    One per user. Professional-managed patients never have one — billing for
    them is handled outside the platform, between Julha and the clinic.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        Index("ix_subscriptions_provider_subscription_id", "provider_subscription_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False, default="asaas")
    status = Column(String, nullable=False, default=SubscriptionStatusEnum.PENDING.value)
    provider_customer_id = Column(String, nullable=True)
    provider_subscription_id = Column(String, nullable=True, unique=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    plan_id = Column(String, nullable=True)
    # True once the user cancels: no more Asaas charges will land, but access
    # (subscription_grants_access) is still honored until current_period_end,
    # matching "cancelamento com efeitos a partir do próximo ciclo" (Termos de
    # Uso §8.2.c) rather than cutting access off immediately.
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    # Set once, on the first PAYMENT_CONFIRMED/PAYMENT_RECEIVED webhook event —
    # the anchor for the 7-day CDC art. 49 withdrawal window (Política de
    # Reembolso §1), which is measured from first payment, not from signup.
    first_paid_at = Column(DateTime(timezone=True), nullable=True)
    # Dunning idempotency markers -- set the first time each lifecycle email
    # goes out so the daily scan (DunningService) doesn't re-send it every
    # day the condition still holds. Cleared when the condition that caused
    # it stops applying (trial extended/converted, cancellation undone).
    trial_ending_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    access_ending_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="subscription")


class NotificationKindEnum(str, enum.Enum):
    PAYMENT_OVERDUE = "PAYMENT_OVERDUE"
    TRIAL_ENDING = "TRIAL_ENDING"
    ACCESS_ENDING = "ACCESS_ENDING"
    PLAN_CHANGED = "PLAN_CHANGED"
    AI_REPORT_READY = "AI_REPORT_READY"
    SYMPTOM_REPORTED = "SYMPTOM_REPORTED"
    PATIENT_ASSIGNED = "PATIENT_ASSIGNED"
    CHECKIN_PENDING = "CHECKIN_PENDING"


class Notification(Base):
    """In-app notification, one row per event. Paired with the dunning
    emails in DunningService (same trigger, two channels) plus a couple of
    other billing events (e.g. a self-service plan change) that are worth
    surfacing in-app even though they don't warrant an email."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_id_created_at", "user_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String, nullable=False)
    message = Column(String, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class PatientLinkRequest(Base):
    """A professional's request to become responsible for an existing patient account.

    Used when a professional tries to add a patient whose email already
    belongs to a self-service (or otherwise unlinked) account — instead of
    silently taking over the account, the professional sends a request the
    patient must accept before any MonitoringPlan/MonitoringProfessional link
    is created.
    """

    __tablename__ = "patient_link_requests"
    __table_args__ = (
        Index("ix_patient_link_requests_patient_status", "patient_user_id", "status"),
        Index("ix_patient_link_requests_professional_status", "professional_profile_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    professional_profile_id = Column(Integer, ForeignKey("professional_profiles.id"), nullable=False)
    patient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default=PatientLinkRequestStatusEnum.PENDING.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)

    professional_profile = relationship("ProfessionalProfile")
    patient = relationship("User", foreign_keys=[patient_user_id])


class AdminCostEntry(Base):
    """A manually recorded operational cost line the admin adds themselves —
    for spend this app has no other visibility into (contracts, tooling,
    support), alongside the AI report / WhatsApp costs computed from data
    the app already tracks.
    """

    __tablename__ = "admin_cost_entries"
    __table_args__ = (
        Index("ix_admin_cost_entries_incurred_on", "incurred_on"),
    )

    id = Column(Integer, primary_key=True)
    description = Column(String, nullable=False)
    category = Column(String, nullable=True)
    amount_cents = Column(Integer, nullable=False)
    incurred_on = Column(Date, nullable=False)
    # A cost that repeats every month from incurred_on onward (e.g. a fixed
    # phone/SIM top-up to keep a number active) instead of a one-off charge —
    # counted once per calendar month it's active in, not re-entered monthly.
    is_recurring = Column(Boolean, nullable=False, default=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
