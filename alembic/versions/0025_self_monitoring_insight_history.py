"""Turn self_monitoring_insights into a history table (one row per generation).

Revision ID: 0025
Revises: 0024
"""

from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_self_monitoring_insights_patient", "self_monitoring_insights", type_="unique")


def downgrade() -> None:
    # Only safe if no patient has more than one row -- delete the extra
    # history rows first (keeping the most recent per patient) if this
    # needs to be rolled back after real data has accumulated.
    op.create_unique_constraint(
        "uq_self_monitoring_insights_patient", "self_monitoring_insights", ["patient_id"]
    )
