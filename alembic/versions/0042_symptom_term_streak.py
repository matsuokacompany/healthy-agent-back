"""Consecutive-occurrence counter on daily_report_symptom_terms, so a
patient answering "mesma dor, mesmo lugar" instead of re-describing a
symptom shows up as persistence (e.g. "há 4 dias") instead of resetting to
a fresh, unrelated-looking entry. Populated by SymptomNormalizationService,
never by the patient directly.

Revision ID: 0042
Revises: 0041
"""

from alembic import op
import sqlalchemy as sa


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_report_symptom_terms",
        sa.Column("streak_days", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("daily_report_symptom_terms", "streak_days")
