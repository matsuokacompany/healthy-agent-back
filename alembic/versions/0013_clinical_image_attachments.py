"""Add private clinical image attachment metadata.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("monitoring_plan_id", sa.Integer(), sa.ForeignKey("monitoring_plans.id"), nullable=True),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("daily_reports.id"), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("whatsapp_message_id", sa.String(), nullable=True, unique=True),
        sa.Column("whatsapp_media_id", sa.String(), nullable=True, unique=True),
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False, unique=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clinical_attachments_patient_created", "clinical_attachments", ["patient_id", "created_at"])
    op.create_index("ix_clinical_attachments_uploader", "clinical_attachments", ["uploaded_by_user_id"])
    op.create_index(
        "uq_clinical_attachments_whatsapp_report",
        "clinical_attachments",
        ["daily_report_id"],
        unique=True,
        postgresql_where=sa.text("source = 'WHATSAPP' AND deleted_at IS NULL"),
    )

    op.execute("ALTER TABLE clinical_attachments ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY clinical_attachments_select ON clinical_attachments
        FOR SELECT USING (
            app_private.service_context()
            OR app_private.can_access_patient(patient_id)
        );
        CREATE POLICY clinical_attachments_insert ON clinical_attachments
        FOR INSERT WITH CHECK (
            app_private.service_context()
            OR (
                app_private.can_access_patient(patient_id)
                AND uploaded_by_user_id = app_private.current_user_id()
            )
        );
        CREATE POLICY clinical_attachments_update ON clinical_attachments
        FOR UPDATE USING (
            app_private.service_context()
            OR (
                app_private.can_access_patient(patient_id)
                AND (
                    patient_id = app_private.current_user_id()
                    OR uploaded_by_user_id = app_private.current_user_id()
                )
            )
        ) WITH CHECK (
            app_private.service_context()
            OR (
                app_private.can_access_patient(patient_id)
                AND (
                    patient_id = app_private.current_user_id()
                    OR uploaded_by_user_id = app_private.current_user_id()
                )
            )
        );
        CREATE POLICY clinical_attachments_delete ON clinical_attachments
        FOR DELETE USING (app_private.service_context());
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clinical_attachments TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE clinical_attachments_id_seq TO healthy_agent_api")


def downgrade() -> None:
    op.drop_table("clinical_attachments")
