"""Add subscription fields for self-service cancel-at-period-end and refund eligibility.

Revision ID: 0024
Revises: 0023
"""

from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("subscriptions", sa.Column("first_paid_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "first_paid_at")
    op.drop_column("subscriptions", "cancel_at_period_end")
