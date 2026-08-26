"""Add bonus_report_credits to monitoring_professionals.

Granted when a patient accepts a link request while still paying for a
self-service subscription — lets the professional bypass the AI report
cooldown for that patient instead of the platform cancelling the
subscription.

Revision ID: 0020
Revises: 0019
"""

from alembic import op
import sqlalchemy as sa


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitoring_professionals",
        sa.Column("bonus_report_credits", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("monitoring_professionals", "bonus_report_credits")
