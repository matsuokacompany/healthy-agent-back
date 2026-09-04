"""Medication/supplement adherence follow-up question for self-service
monitoring plans, asked as an extra step in the same daily WhatsApp
conversation right after the symptom question.

Revision ID: 0029
Revises: 0028
"""

from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TYPE dailyreportstatusenum ADD VALUE IF NOT EXISTS 'AWAITING_MEDICATION_ADHERENCE';
        END
        $$;
        """
    )
    op.add_column("daily_reports", sa.Column("medication_adherence", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_reports", "medication_adherence")
    # Postgres has no ALTER TYPE ... DROP VALUE — the enum label stays,
    # matching how this codebase already handles enum additions (see 0001).
