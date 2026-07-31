"""custom ai report foundation

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_report_cache", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column(
        "ai_report_cache",
        sa.Column("status", sa.String(), nullable=False, server_default="COMPLETED"),
    )
    op.add_column(
        "ai_report_cache",
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column("ai_report_cache", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_report_cache", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_report_cache", sa.Column("next_generation_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_report_cache", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("estimated_cost", sa.Numeric(12, 8), nullable=True))
    op.add_column("ai_report_cache", sa.Column("actual_cost", sa.Numeric(12, 8), nullable=True))
    op.add_column("ai_report_cache", sa.Column("model_name", sa.String(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("prompt_version", sa.String(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("failure_code", sa.String(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("failure_message", sa.Text(), nullable=True))
    op.add_column("ai_report_cache", sa.Column("idempotency_key", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE ai_report_cache
        SET requested_at = created_at,
            generated_at = created_at,
            next_generation_at = created_at + INTERVAL '30 days'
        """
    )

    op.alter_column("ai_report_cache", "clinical_summary_hash", existing_type=sa.String(), nullable=True)
    op.alter_column("ai_report_cache", "clinical_summary", existing_type=sa.Text(), nullable=True)
    op.alter_column("ai_report_cache", "ai_response", existing_type=sa.JSON(), nullable=True)

    op.create_index(
        "ix_ai_report_cache_patient_status_generated",
        "ai_report_cache",
        ["patient_id", "status", "generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_report_cache_patient_dates",
        "ai_report_cache",
        ["patient_id", "start_date", "end_date"],
        unique=False,
    )
    op.create_index(
        "ix_ai_report_cache_idempotency_key",
        "ai_report_cache",
        ["idempotency_key"],
        unique=True,
    )


def downgrade():
    op.execute(
        """
        UPDATE ai_report_cache
        SET clinical_summary_hash = COALESCE(clinical_summary_hash, ''),
            clinical_summary = COALESCE(clinical_summary, ''),
            ai_response = COALESCE(ai_response, '{}'::json)
        """
    )

    op.drop_index("ix_ai_report_cache_idempotency_key", table_name="ai_report_cache")
    op.drop_index("ix_ai_report_cache_patient_dates", table_name="ai_report_cache")
    op.drop_index("ix_ai_report_cache_patient_status_generated", table_name="ai_report_cache")

    op.alter_column("ai_report_cache", "ai_response", existing_type=sa.JSON(), nullable=False)
    op.alter_column("ai_report_cache", "clinical_summary", existing_type=sa.Text(), nullable=False)
    op.alter_column("ai_report_cache", "clinical_summary_hash", existing_type=sa.String(), nullable=False)

    for column_name in (
        "idempotency_key",
        "failure_message",
        "failure_code",
        "prompt_version",
        "model_name",
        "actual_cost",
        "estimated_cost",
        "output_tokens",
        "input_tokens",
        "next_generation_at",
        "generated_at",
        "processing_started_at",
        "requested_at",
        "status",
        "end_date",
        "start_date",
    ):
        op.drop_column("ai_report_cache", column_name)
