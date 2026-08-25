"""Add subscriptions table for self-service (B2C) Asaas billing.

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="asaas"),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("provider_customer_id", sa.String(), nullable=True),
        sa.Column("provider_subscription_id", sa.String(), nullable=True, unique=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
    )
    op.create_index(
        "ix_subscriptions_provider_subscription_id",
        "subscriptions",
        ["provider_subscription_id"],
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON subscriptions TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE subscriptions_id_seq TO healthy_agent_api")

    # Row Level Security, matching the pattern in 0009_row_level_security.py:
    # a user can only see/manage their own subscription; service context
    # (webhook handler) and admins bypass this.
    op.execute("ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY subscriptions_select ON subscriptions FOR SELECT USING (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR user_id = app_private.current_user_id()
        );
        CREATE POLICY subscriptions_insert ON subscriptions FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR user_id = app_private.current_user_id()
        );
        CREATE POLICY subscriptions_update ON subscriptions FOR UPDATE
            USING (app_private.service_context() OR app_private.current_user_is_admin())
            WITH CHECK (app_private.service_context() OR app_private.current_user_is_admin());
        CREATE POLICY subscriptions_delete ON subscriptions FOR DELETE USING (
            app_private.service_context() OR app_private.current_user_is_admin()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS subscriptions_select ON subscriptions")
    op.execute("DROP POLICY IF EXISTS subscriptions_insert ON subscriptions")
    op.execute("DROP POLICY IF EXISTS subscriptions_update ON subscriptions")
    op.execute("DROP POLICY IF EXISTS subscriptions_delete ON subscriptions")
    op.drop_index("ix_subscriptions_provider_subscription_id", table_name="subscriptions")
    op.drop_table("subscriptions")
