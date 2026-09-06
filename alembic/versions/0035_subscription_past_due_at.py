"""Track when a subscription first became PAST_DUE, so the daily dunning
scan can auto-cancel it once it's stayed unpaid past the grace period.

Revision ID: 0035
Revises: 0034
"""

from alembic import op
import sqlalchemy as sa


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("past_due_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "past_due_at")
