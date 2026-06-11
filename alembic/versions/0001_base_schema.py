"""base schema

Revision ID: 0001
Revises: 
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # =========================================================
    # USERS (sem FK circular pesada)
    # =========================================================
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("telegram_id", sa.String, unique=True, index=True),
        sa.Column("phone", sa.String),
        sa.Column("city", sa.String),
        sa.Column("state", sa.String),
        sa.Column("gender", sa.String),
        sa.Column("birth_date", sa.Date),
        sa.Column("cpf", sa.String, unique=True),
        sa.Column("hashed_password", sa.String),
        sa.Column("is_admin", sa.Boolean, default=False),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

        sa.Column("current_report_id", sa.Integer, nullable=True),
        sa.Column("pending_check_type", sa.String, nullable=True),
        sa.Column("pending_report_date", sa.Date, nullable=True),
        sa.Column("pending_prompt_sent_at", sa.DateTime(timezone=True)),
    )

    # =========================================================
    # ANAMNESES
    # =========================================================
    op.create_table(
        "anamneses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("info", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # =========================================================
    # REFRESH TOKENS
    # =========================================================
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String, unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # =========================================================
    # TELEGRAM LINK CODES
    # =========================================================
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String, unique=True, index=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, default=False),
    )

    # =========================================================
    # DAILY REPORTS (depois de users existir)
    # =========================================================
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("report_date", sa.Date, nullable=False, index=True),
        sa.Column("check_type", sa.String, nullable=False, index=True),
        sa.Column("symptom_description", sa.Text),
        sa.Column("suspected_cause", sa.Text),
        sa.Column("had_symptoms", sa.Boolean, nullable=False),
        sa.Column("completed", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),

        sa.UniqueConstraint(
            "user_id",
            "report_date",
            "check_type",
            name="uq_user_report_date_check"
        )
    )

    # =========================================================
    # INDEXES EXTRAS (opcional, mas recomendado)
    # =========================================================
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_daily_reports_user_id", "daily_reports", ["user_id"])


def downgrade():
    op.drop_table("daily_reports")
    op.drop_table("telegram_link_codes")
    op.drop_table("refresh_tokens")
    op.drop_table("anamneses")
    op.drop_table("users")