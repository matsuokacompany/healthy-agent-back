"""Lifestyle adherence follow-up (diet + medication/supplement) for
self-service monitoring plans, asked as one combined free-text question in
the same daily WhatsApp conversation right after the symptom question.

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
    op.add_column("daily_reports", sa.Column("diet_adherence", sa.Boolean(), nullable=True))
    op.add_column("daily_reports", sa.Column("medication_adherence", sa.Boolean(), nullable=True))
    op.add_column("daily_reports", sa.Column("lifestyle_notes", sa.Text(), nullable=True))
    op.add_column("daily_reports", sa.Column("lifestyle_notes_encryption_envelope", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_reports", "lifestyle_notes_encryption_envelope")
    op.drop_column("daily_reports", "lifestyle_notes")
    op.drop_column("daily_reports", "medication_adherence")
    op.drop_column("daily_reports", "diet_adherence")
    # Postgres has no ALTER TYPE ... DROP VALUE — the enum label stays,
    # matching how this codebase already handles enum additions (see 0001).
