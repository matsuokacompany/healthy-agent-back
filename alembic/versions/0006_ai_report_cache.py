"""ai report cache

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_report_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("professional_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("periodo", sa.String(), nullable=False),
        sa.Column("modo", sa.String(), nullable=False),
        sa.Column("clinical_summary_hash", sa.String(), nullable=False),
        sa.Column("clinical_summary", sa.Text(), nullable=False),
        sa.Column("ai_response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_report_cache_patient_created",
        "ai_report_cache",
        ["patient_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_report_cache_professional_created",
        "ai_report_cache",
        ["professional_user_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_ai_report_cache_professional_created", table_name="ai_report_cache")
    op.drop_index("ix_ai_report_cache_patient_created", table_name="ai_report_cache")
    op.drop_table("ai_report_cache")
