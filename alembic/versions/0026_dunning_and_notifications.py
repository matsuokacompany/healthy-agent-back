"""Add dunning reminder markers on subscriptions and a notifications table.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("trial_ending_reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("access_ending_reminder_sent_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_notifications_user_id_created_at", "notifications", ["user_id", "created_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE notifications_id_seq TO healthy_agent_api")

    # Row Level Security, matching the pattern in 0015_subscriptions.py.
    # Notifications are always system-generated (dunning/billing events), so
    # inserts/deletes are service-context (or admin) only; a user reads and
    # can mark-as-read only their own rows.
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY notifications_select ON notifications FOR SELECT USING (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR user_id = app_private.current_user_id()
        )
        """
    )
    op.execute(
        """
        CREATE POLICY notifications_insert ON notifications FOR INSERT WITH CHECK (
            app_private.service_context() OR app_private.current_user_is_admin()
        )
        """
    )
    op.execute(
        """
        CREATE POLICY notifications_update ON notifications FOR UPDATE
            USING (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR user_id = app_private.current_user_id()
            )
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR user_id = app_private.current_user_id()
            )
        """
    )
    op.execute(
        """
        CREATE POLICY notifications_delete ON notifications FOR DELETE USING (
            app_private.service_context() OR app_private.current_user_is_admin()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS notifications_delete ON notifications")
    op.execute("DROP POLICY IF EXISTS notifications_update ON notifications")
    op.execute("DROP POLICY IF EXISTS notifications_insert ON notifications")
    op.execute("DROP POLICY IF EXISTS notifications_select ON notifications")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("subscriptions", "access_ending_reminder_sent_at")
    op.drop_column("subscriptions", "trial_ending_reminder_sent_at")
