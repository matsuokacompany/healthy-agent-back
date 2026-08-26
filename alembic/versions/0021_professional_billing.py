"""Add free_until grace period to professional_profiles for professional billing.

Revision ID: 0021
Revises: 0020
"""

from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

# All professional accounts that already exist as of this rollout keep free
# access until this date (start of "next year" from the product decision
# behind this migration). New signups get NULL and must subscribe.
GRANDFATHER_FREE_UNTIL = "2027-01-01"


def upgrade() -> None:
    op.add_column("professional_profiles", sa.Column("free_until", sa.Date(), nullable=True))
    op.execute(
        f"UPDATE professional_profiles SET free_until = '{GRANDFATHER_FREE_UNTIL}'"
    )


def downgrade() -> None:
    op.drop_column("professional_profiles", "free_until")
