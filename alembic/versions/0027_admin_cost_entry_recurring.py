"""Add admin_cost_entries.is_recurring for fixed monthly costs.

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_cost_entries",
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("admin_cost_entries", "is_recurring")
