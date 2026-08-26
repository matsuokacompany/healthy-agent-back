"""Add admin_cost_entries for manually recorded admin cost lines.

Revision ID: 0022
Revises: 0021
"""

from alembic import op
import sqlalchemy as sa


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_cost_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_cost_entries_incurred_on", "admin_cost_entries", ["incurred_on"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON admin_cost_entries TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE admin_cost_entries_id_seq TO healthy_agent_api")

    # Row Level Security, matching the pattern in 0009_row_level_security.py.
    # Admin-only table: nobody else has any business reading or writing
    # manually entered operational cost lines.
    op.execute("ALTER TABLE admin_cost_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE admin_cost_entries FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY admin_cost_entries_all ON admin_cost_entries FOR ALL
            USING (app_private.service_context() OR app_private.current_user_is_admin())
            WITH CHECK (app_private.service_context() OR app_private.current_user_is_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS admin_cost_entries_all ON admin_cost_entries")
    op.drop_index("ix_admin_cost_entries_incurred_on", table_name="admin_cost_entries")
    op.drop_table("admin_cost_entries")
