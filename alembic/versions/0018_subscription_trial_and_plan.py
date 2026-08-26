"""Add trial_ends_at/plan_id to subscriptions for the free-trial + multi-plan billing feature.

Revision ID: 0018
Revises: 0017
"""

from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("plan_id", sa.String(), nullable=True))

    # Backfill: any pre-existing PENDING subscription row predates the trial
    # concept — grant it the same 30-day trial retroactively (measured from
    # when the row was created) instead of leaving it with no access at all
    # once TRIALING/ACTIVE become the only statuses that grant access.
    op.execute(
        """
        UPDATE subscriptions
        SET status = 'TRIALING', trial_ends_at = created_at + interval '30 days'
        WHERE status = 'PENDING' AND trial_ends_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "plan_id")
    op.drop_column("subscriptions", "trial_ends_at")
