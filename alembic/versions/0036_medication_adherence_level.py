"""Track whether the patient took all, some, or none of their registered
supplements/medications -- finer-grained than the existing
medication_adherence boolean, which only distinguishes "all" from
"anything less than all".

Revision ID: 0036
Revises: 0035
"""

from alembic import op
import sqlalchemy as sa


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_reports", sa.Column("medication_adherence_level", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_reports", "medication_adherence_level")
