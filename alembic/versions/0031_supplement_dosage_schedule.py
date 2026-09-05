"""Add a dosage schedule (times per day/week/month, plus an optional
duration) to patient-managed supplements, so the professional can set it at
patient creation and the self-service patient can set it on their own list.

Revision ID: 0031
Revises: 0030
"""

from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplements", sa.Column("dosage_times", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "supplements", sa.Column("dosage_period", sa.String(), nullable=False, server_default="DAY")
    )
    op.add_column(
        "supplements",
        sa.Column("started_at", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
    )
    # NULL means indeterminate/ongoing -- no server_default, existing rows
    # keep behaving like they always did (asked about forever).
    op.add_column("supplements", sa.Column("duration_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("supplements", "duration_days")
    op.drop_column("supplements", "started_at")
    op.drop_column("supplements", "dosage_period")
    op.drop_column("supplements", "dosage_times")
