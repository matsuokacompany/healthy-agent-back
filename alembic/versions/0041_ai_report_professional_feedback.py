"""Nullable professional feedback ("up"/"down") on ai_report_cache -- lets a
professional flag whether an AI-generated report's hypothesis was useful,
right from the report view, instead of relying only on a manual physician
review of a separate golden case set to gauge real-world accuracy.

Revision ID: 0041
Revises: 0040
"""

from alembic import op
import sqlalchemy as sa


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_report_cache", sa.Column("professional_feedback", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_report_cache", "professional_feedback")
