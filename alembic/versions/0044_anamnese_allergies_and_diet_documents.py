"""Adds allergy/restriction fields to anamneses (medication allergies and
food restrictions, same envelope-encrypted-text pattern as `info`) and a new
`diet_documents` table -- one active diet-plan PDF per patient, stored the
same way clinical images are (Supabase Storage, only metadata in Postgres),
but through a separate bucket/content-type since ClinicalAttachmentService's
Pillow pipeline only ever accepts and produces JPEG.

Both exist to make a patient's own data useful to a health professional --
whether that's a professional already reviewing them on the platform, or one
the patient (typically a self-monitoring patient with nobody assigned) is
about to see and wants to hand a summary to.

Revision ID: 0044
Revises: 0043
"""

from alembic import op
import sqlalchemy as sa


revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("anamneses", sa.Column("medication_allergies", sa.Text(), nullable=True))
    op.add_column("anamneses", sa.Column("medication_allergies_encryption_envelope", sa.JSON(), nullable=True))
    op.add_column("anamneses", sa.Column("food_restrictions", sa.Text(), nullable=True))
    op.add_column("anamneses", sa.Column("food_restrictions_encryption_envelope", sa.JSON(), nullable=True))

    op.create_table(
        "diet_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_diet_documents_uploader", "diet_documents", ["uploaded_by_user_id"])

    op.execute("ALTER TABLE diet_documents ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY diet_documents_select ON diet_documents
        FOR SELECT USING (
            app_private.service_context()
            OR app_private.can_access_patient(patient_id)
        );
        CREATE POLICY diet_documents_insert ON diet_documents
        FOR INSERT WITH CHECK (
            app_private.service_context()
            OR (
                app_private.can_access_patient(patient_id)
                AND uploaded_by_user_id = app_private.current_user_id()
            )
        );
        CREATE POLICY diet_documents_update ON diet_documents
        FOR UPDATE USING (
            app_private.service_context()
            OR app_private.can_access_patient(patient_id)
        ) WITH CHECK (
            app_private.service_context()
            OR (
                app_private.can_access_patient(patient_id)
                AND uploaded_by_user_id = app_private.current_user_id()
            )
        );
        CREATE POLICY diet_documents_delete ON diet_documents
        FOR DELETE USING (
            app_private.service_context()
            OR app_private.can_access_patient(patient_id)
        );
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON diet_documents TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE diet_documents_id_seq TO healthy_agent_api")


def downgrade() -> None:
    op.drop_table("diet_documents")
    op.drop_column("anamneses", "food_restrictions_encryption_envelope")
    op.drop_column("anamneses", "food_restrictions")
    op.drop_column("anamneses", "medication_allergies_encryption_envelope")
    op.drop_column("anamneses", "medication_allergies")
