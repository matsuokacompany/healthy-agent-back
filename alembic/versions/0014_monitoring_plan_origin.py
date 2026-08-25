"""Add monitoring_plans.origin to distinguish self-service from professional-managed plans.

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitoring_plans",
        sa.Column("origin", sa.String(), nullable=False, server_default="PROFESSIONAL"),
    )


def downgrade() -> None:
    op.drop_column("monitoring_plans", "origin")
