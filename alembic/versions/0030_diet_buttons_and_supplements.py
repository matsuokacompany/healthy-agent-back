"""Split the self-service lifestyle follow-up into deterministic WhatsApp
button questions (diet, then medication) instead of one AI-parsed free-text
reply, and add a patient-managed supplement list used to name the
medication question instead of asking generically.

Revision ID: 0030
Revises: 0029
"""

from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TYPE dailyreportstatusenum ADD VALUE IF NOT EXISTS 'AWAITING_DIET_ADHERENCE';
            ALTER TYPE dailyreportstatusenum ADD VALUE IF NOT EXISTS 'AWAITING_DIET_DEVIATION_DESCRIPTION';
        END
        $$;
        """
    )

    op.create_table(
        "supplements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_supplements_patient_id", "supplements", ["patient_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON supplements TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE supplements_id_seq TO healthy_agent_api")

    op.execute("ALTER TABLE supplements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE supplements FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        -- Read: the patient themselves, or a professional linked to them
        -- (same visibility as clinical_attachments) -- a future professional
        -- plan for this patient should still be able to see the list.
        CREATE POLICY supplements_select ON supplements FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(patient_id)
        )
        """
    )
    op.execute(
        """
        -- Write: the patient's own list only -- self-managed, unlike
        -- Anamnese.info which is professional-authored (see
        -- anamnese_routes.py's _require_clinical_write_access).
        CREATE POLICY supplements_write ON supplements FOR ALL
            USING (app_private.service_context() OR patient_id = app_private.current_user_id())
            WITH CHECK (app_private.service_context() OR patient_id = app_private.current_user_id())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS supplements_select ON supplements")
    op.execute("DROP POLICY IF EXISTS supplements_write ON supplements")
    op.drop_table("supplements")
    # Postgres has no ALTER TYPE ... DROP VALUE — the enum labels stay,
    # matching how this codebase already handles enum additions (see 0001).
