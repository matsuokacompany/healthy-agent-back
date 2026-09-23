"""Adds a patient-managed, structured allergy list (allergen + severity),
same shape and RLS pattern as `supplements` -- distinct from
`anamneses.medication_allergies`/`food_restrictions`, which stay as
professional-authored free text. This one is meant for a patient to log
each allergy as its own row with a severity level (e.g. a seafood allergy
severe enough to be life-threatening), the same "add a row" UX already used
for supplements, so it reads clearly on the clinical handoff summary instead
of being buried in prose.

Revision ID: 0046
Revises: 0045
"""

from alembic import op
import sqlalchemy as sa


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allergies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("allergen", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="MODERADA"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_allergies_patient_id", "allergies", ["patient_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON allergies TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE allergies_id_seq TO healthy_agent_api")

    op.execute("ALTER TABLE allergies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE allergies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        -- Read: the patient themselves, or a professional linked to them --
        -- same visibility as supplements/clinical_attachments.
        CREATE POLICY allergies_select ON allergies FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(patient_id)
        )
        """
    )
    op.execute(
        """
        -- Write: the patient's own list, or a professional actively linked
        -- to them -- same final rule supplements_write settled on
        -- (0030 + 0032), written directly here since this table is new.
        CREATE POLICY allergies_write ON allergies FOR ALL
            USING (app_private.service_context() OR app_private.can_access_patient(patient_id))
            WITH CHECK (app_private.service_context() OR app_private.can_access_patient(patient_id))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS allergies_select ON allergies")
    op.execute("DROP POLICY IF EXISTS allergies_write ON allergies")
    op.drop_table("allergies")
