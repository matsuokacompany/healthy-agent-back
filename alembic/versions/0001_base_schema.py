"""base schema

Revision ID: 0001
Revises: 
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    # =========================================================
    # USERS
    # =========================================================
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("telegram_id", sa.String),
        sa.Column("phone", sa.String),
        sa.Column("city", sa.String),
        sa.Column("state", sa.String),
        sa.Column("gender", sa.String),
        sa.Column("birth_date", sa.Date),
        sa.Column("cpf", sa.String),
        sa.Column("hashed_password", sa.String),
        sa.Column("is_admin", sa.Boolean, server_default=sa.text("false")),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("current_report_id", sa.Integer),
        sa.Column("pending_check_type", sa.String),
        sa.Column("pending_report_date", sa.Date),
        sa.Column("pending_prompt_sent_at", sa.DateTime(timezone=True)),
    )

    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)


    # =========================================================
    # ANAMNESES
    # =========================================================
    op.create_table(
        "anamneses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("info", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


    # =========================================================
    # REFRESH TOKENS
    # =========================================================
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


    # =========================================================
    # TELEGRAM LINK CODES
    # =========================================================
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, server_default=sa.text("false")),
    )

    op.create_index("ix_telegram_link_codes_code", "telegram_link_codes", ["code"], unique=True)


    # =========================================================
    # DAILY REPORTS
    # =========================================================
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("check_type", sa.String, nullable=False),

        sa.Column("symptom_description", sa.Text),
        sa.Column("suspected_cause", sa.Text),
        sa.Column("had_symptoms", sa.Boolean, nullable=False),
        sa.Column("completed", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),

        sa.UniqueConstraint(
            "user_id",
            "report_date",
            "check_type",
            name="uq_user_report_date_check"
        )
    )

    op.create_index("ix_daily_reports_user_id", "daily_reports", ["user_id"])
    op.create_index("ix_daily_reports_report_date", "daily_reports", ["report_date"])


def downgrade():

    op.drop_table("daily_reports")
    op.drop_table("telegram_link_codes")
    op.drop_table("refresh_tokens")
    op.drop_table("anamneses")
    op.drop_table("users")