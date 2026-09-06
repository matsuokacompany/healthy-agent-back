"""Add an exercise-adherence question ("você treinou ontem?") to the daily
WhatsApp check-in, asked right after diet and before medication/supplements.
Also makes the medication question skippable when the patient has no
active supplements registered.

Revision ID: 0034
Revises: 0033
"""

from alembic import op
import sqlalchemy as sa


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TYPE dailyreportstatusenum ADD VALUE IF NOT EXISTS 'AWAITING_EXERCISE_ADHERENCE';
        END
        $$;
        """
    )
    op.add_column("daily_reports", sa.Column("exercise_adherence", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_reports", "exercise_adherence")
    # Postgres has no ALTER TYPE ... DROP VALUE — the enum label stays,
    # matching how this codebase already handles enum additions (see 0001).
