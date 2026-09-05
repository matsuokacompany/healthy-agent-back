"""Let a professional actively linked to a patient manage that patient's
supplement list too, not just the patient themselves -- same
`can_access_patient` rule already used for Anamnese.info, so a professional
can register/adjust dosage for a patient they're monitoring (patient detail
page), not only at intake.

Revision ID: 0032
Revises: 0031
"""

from alembic import op


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS supplements_write ON supplements")
    op.execute(
        """
        CREATE POLICY supplements_write ON supplements FOR ALL
            USING (app_private.service_context() OR app_private.can_access_patient(patient_id))
            WITH CHECK (app_private.service_context() OR app_private.can_access_patient(patient_id))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS supplements_write ON supplements")
    op.execute(
        """
        CREATE POLICY supplements_write ON supplements FOR ALL
            USING (app_private.service_context() OR patient_id = app_private.current_user_id())
            WITH CHECK (app_private.service_context() OR patient_id = app_private.current_user_id())
        """
    )
