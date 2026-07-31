"""prevent concurrent ai report generations

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_ai_report_cache_patient_active",
        "ai_report_cache",
        ["patient_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'PROCESSING')"),
    )


def downgrade():
    op.drop_index("uq_ai_report_cache_patient_active", table_name="ai_report_cache")
