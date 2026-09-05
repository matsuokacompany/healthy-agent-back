"""Track whether the patient (and their professional) were already
notified that a supplement's course ended, and add the
SUPPLEMENT_COURSE_ENDED notification kind.

Revision ID: 0033
Revises: 0032
"""

from alembic import op
import sqlalchemy as sa


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplements", sa.Column("ended_notification_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("supplements", "ended_notification_sent_at")
    # notifications.kind is a plain string column (no DB-level enum), so
    # there's nothing to revert for SUPPLEMENT_COURSE_ENDED.
