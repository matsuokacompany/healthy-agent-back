"""add nullable clinical encryption envelopes

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("anamneses", sa.Column("info_encryption_envelope", sa.JSON(), nullable=True))
    op.add_column(
        "daily_reports",
        sa.Column("symptom_description_encryption_envelope", sa.JSON(), nullable=True),
    )
    op.add_column(
        "daily_reports",
        sa.Column("suspected_cause_encryption_envelope", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_report_cache",
        sa.Column("clinical_summary_encryption_envelope", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_report_cache",
        sa.Column("ai_response_encryption_envelope", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_report_cache", "ai_response_encryption_envelope")
    op.drop_column("ai_report_cache", "clinical_summary_encryption_envelope")
    op.drop_column("daily_reports", "suspected_cause_encryption_envelope")
    op.drop_column("daily_reports", "symptom_description_encryption_envelope")
    op.drop_column("anamneses", "info_encryption_envelope")
