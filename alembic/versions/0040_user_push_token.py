"""Nullable push-notification token on User, unused until a mobile app
exists to register one -- this is the groundwork for routing red-flag
alerts (see red_flag_symptoms.py/notification_service.py) to a phone push
instead of only the in-app Notification bell. One opaque string column
works for any provider's token format (FCM, APNs, Expo); which provider
to integrate is a decision for when the app actually exists, not now.

Revision ID: 0040
Revises: 0039
"""

from alembic import op
import sqlalchemy as sa


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("push_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "push_token")
