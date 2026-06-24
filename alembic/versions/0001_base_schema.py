"""base schema

Revision ID: 0001
Revises:
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

check_type_enum = sa.Enum("MORNING", "NIGHT", name="checktypeenum")
daily_report_status_enum = sa.Enum("PENDING", "AWAITING_CAUSE", "COMPLETED", "EXPIRED", name="dailyreportstatusenum")


def upgrade():
    bind = op.get_bind()
    check_type_enum.create(bind, checkfirst=True)
    daily_report_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("telegram_id", sa.String, nullable=True),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("city", sa.String, nullable=True),
        sa.Column("state", sa.String, nullable=True),
        sa.Column("gender", sa.String, nullable=True),
        sa.Column("birth_date", sa.Date, nullable=True),
        sa.Column("cpf", sa.String, nullable=True),
        sa.Column("hashed_password", sa.String, nullable=True),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("cpf"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=False)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "anamneses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("info", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "professional_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("license_number", sa.String, nullable=True),
        sa.Column("license_state", sa.String, nullable=True),
        sa.Column("specialty", sa.String, nullable=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("license_number", "license_state", name="uq_professional_license"),
    )

    op.create_table(
        "monitoring_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_monitoring_plans_patient_id", "monitoring_plans", ["patient_id"], unique=False)
    op.create_index("ix_monitoring_plans_active_dates", "monitoring_plans", ["active", "start_date", "end_date"], unique=False)

    op.create_table(
        "monitoring_professionals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("monitoring_plan_id", sa.Integer, sa.ForeignKey("monitoring_plans.id"), nullable=False),
        sa.Column("professional_profile_id", sa.Integer, sa.ForeignKey("professional_profiles.id"), nullable=False),
        sa.Column("role", sa.String, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("monitoring_plan_id", "professional_profile_id", name="uq_monitoring_plan_professional"),
    )
    op.create_index("ix_monitoring_professionals_plan_id", "monitoring_professionals", ["monitoring_plan_id"], unique=False)
    op.create_index("ix_monitoring_professionals_professional_id", "monitoring_professionals", ["professional_profile_id"], unique=False)

    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("monitoring_plan_id", sa.Integer, sa.ForeignKey("monitoring_plans.id"), nullable=False),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("check_type", check_type_enum, nullable=False),
        sa.Column("status", daily_report_status_enum, nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("symptom_description", sa.Text, nullable=True),
        sa.Column("suspected_cause", sa.Text, nullable=True),
        sa.Column("had_symptoms", sa.Boolean, nullable=True),
        sa.Column("completed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("awaiting_response", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("awaiting_cause", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("prompt_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("monitoring_plan_id", "report_date", "check_type", name="uq_plan_report_date_check"),
    )
    op.create_index("ix_daily_reports_user_id", "daily_reports", ["user_id"], unique=False)
    op.create_index("ix_daily_reports_monitoring_plan_id", "daily_reports", ["monitoring_plan_id"], unique=False)
    op.create_index("ix_daily_reports_report_date", "daily_reports", ["report_date"], unique=False)
    op.create_index("ix_daily_reports_status", "daily_reports", ["status"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"], unique=True)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False)

    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_telegram_link_codes_code", "telegram_link_codes", ["code"], unique=True)


def downgrade():
    op.drop_table("telegram_link_codes")
    op.drop_table("refresh_tokens")
    op.drop_table("daily_reports")
    op.drop_table("monitoring_professionals")
    op.drop_table("monitoring_plans")
    op.drop_table("professional_profiles")
    op.drop_table("anamneses")
    op.drop_table("users")
    daily_report_status_enum.drop(op.get_bind(), checkfirst=True)
    check_type_enum.drop(op.get_bind(), checkfirst=True)
