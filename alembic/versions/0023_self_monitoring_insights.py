"""Add self_monitoring_insights for the self_made (B2C) patient AI evolution summary.

Revision ID: 0023
Revises: 0022
"""

from alembic import op
import sqlalchemy as sa


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "self_monitoring_insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("insight_response", sa.JSON(), nullable=True),
        sa.Column("insight_response_encryption_envelope", sa.JSON(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 8), nullable=True),
        sa.Column("actual_cost", sa.Numeric(12, 8), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("next_generation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_self_monitoring_insights_patient", "self_monitoring_insights", ["patient_id"]
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON self_monitoring_insights TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE self_monitoring_insights_id_seq TO healthy_agent_api")

    # Row Level Security, matching the pattern in 0009_row_level_security.py.
    # Patients read their own row directly (no professional in this flow);
    # writes are system-generated (the AI call result), so restricted to
    # service context only, same reasoning as monitoring_plans_insert for
    # self_monitoring_provisioning.
    op.execute("ALTER TABLE self_monitoring_insights ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE self_monitoring_insights FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY self_monitoring_insights_select ON self_monitoring_insights FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(patient_id)
        )
        """
    )
    op.execute(
        """
        CREATE POLICY self_monitoring_insights_write ON self_monitoring_insights FOR ALL
            USING (app_private.service_context())
            WITH CHECK (app_private.service_context())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS self_monitoring_insights_select ON self_monitoring_insights")
    op.execute("DROP POLICY IF EXISTS self_monitoring_insights_write ON self_monitoring_insights")
    op.drop_constraint("uq_self_monitoring_insights_patient", "self_monitoring_insights", type_="unique")
    op.drop_table("self_monitoring_insights")
