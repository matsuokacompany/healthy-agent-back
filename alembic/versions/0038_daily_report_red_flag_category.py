"""Record which reviewed RED_FLAG_ABSOLUTE category (if any) a check-in's
free-text symptom description matched -- see
app/services/red_flag_symptoms.py and RedFlagDetectionService. A short
category key, not free text, so it doesn't need the envelope-encryption
treatment symptom_description gets.

Revision ID: 0038
Revises: 0037
"""

from alembic import op
import sqlalchemy as sa


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_reports", sa.Column("red_flag_category", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_reports", "red_flag_category")
