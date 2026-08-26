"""Add patient_link_requests for professional -> existing-patient linking.

Revision ID: 0019
Revises: 0018
"""

from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_link_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("professional_profile_id", sa.Integer(), sa.ForeignKey("professional_profiles.id"), nullable=False),
        sa.Column("patient_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_patient_link_requests_patient_status",
        "patient_link_requests",
        ["patient_user_id", "status"],
    )
    op.create_index(
        "ix_patient_link_requests_professional_status",
        "patient_link_requests",
        ["professional_profile_id", "status"],
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_link_requests TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE patient_link_requests_id_seq TO healthy_agent_api")

    # Row Level Security, matching the pattern in 0009_row_level_security.py:
    # the sending professional and the target patient can see the request;
    # only the patient (or service context) can update it (accept/reject) —
    # the actual link/plan creation on accept always runs under service
    # context, same as self_monitoring_provisioning.
    op.execute("ALTER TABLE patient_link_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patient_link_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY patient_link_requests_select ON patient_link_requests FOR SELECT USING (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR patient_user_id = app_private.current_user_id()
            OR EXISTS (
                SELECT 1 FROM professional_profiles pp
                WHERE pp.id = patient_link_requests.professional_profile_id
                  AND pp.user_id = app_private.current_user_id()
            )
        );
        CREATE POLICY patient_link_requests_insert ON patient_link_requests FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR EXISTS (
                SELECT 1 FROM professional_profiles pp
                WHERE pp.id = patient_link_requests.professional_profile_id
                  AND pp.user_id = app_private.current_user_id()
            )
        );
        CREATE POLICY patient_link_requests_update ON patient_link_requests FOR UPDATE
            USING (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR patient_user_id = app_private.current_user_id()
            )
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR patient_user_id = app_private.current_user_id()
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_link_requests_select ON patient_link_requests")
    op.execute("DROP POLICY IF EXISTS patient_link_requests_insert ON patient_link_requests")
    op.execute("DROP POLICY IF EXISTS patient_link_requests_update ON patient_link_requests")
    op.drop_index("ix_patient_link_requests_professional_status", table_name="patient_link_requests")
    op.drop_index("ix_patient_link_requests_patient_status", table_name="patient_link_requests")
    op.drop_table("patient_link_requests")
