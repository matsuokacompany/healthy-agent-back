"""Add a database-level backstop for the anamnese self-write/professional
handoff rule: app/routes/anamnese_routes.py already blocks a patient from
writing their own anamnese once an active PROFESSIONAL-origin monitoring
plan links them (self-write is only for a self-service patient with nobody
to ask), but that rule previously lived only in the API layer -- the RLS
policy on `anamneses` allowed a patient to write their own row unconditionally
via app_private.can_access_patient(). This adds a narrow, anamneses-specific
policy so a future regression in the API check is still caught at the
database layer, without touching can_access_patient() itself (used broadly
by other tables) or this table's SELECT/DELETE policies.

Revision ID: 0037
Revises: 0036
"""

from alembic import op


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.patient_has_active_professional_plan(target_patient_id integer)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM monitoring_plans
                WHERE patient_id = target_patient_id
                  AND origin = 'PROFESSIONAL'
                  AND active IS TRUE
            )
        $$
        """
    )
    op.execute("DROP POLICY IF EXISTS anamneses_insert ON anamneses")
    op.execute("DROP POLICY IF EXISTS anamneses_update ON anamneses")
    op.execute(
        """
        CREATE POLICY anamneses_insert ON anamneses FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR (
                anamneses.user_id = app_private.current_user_id()
                AND NOT app_private.patient_has_active_professional_plan(anamneses.user_id)
            )
            OR EXISTS (
                SELECT 1
                FROM professional_profiles pp
                JOIN monitoring_professionals mp
                  ON mp.professional_profile_id = pp.id
                JOIN monitoring_plans plan
                  ON plan.id = mp.monitoring_plan_id
                WHERE pp.user_id = app_private.current_user_id()
                  AND pp.active IS TRUE
                  AND mp.active IS TRUE
                  AND plan.active IS TRUE
                  AND plan.patient_id = anamneses.user_id
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY anamneses_update ON anamneses FOR UPDATE
            USING (app_private.service_context() OR app_private.can_access_patient(user_id))
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR (
                    anamneses.user_id = app_private.current_user_id()
                    AND NOT app_private.patient_has_active_professional_plan(anamneses.user_id)
                )
                OR EXISTS (
                    SELECT 1
                    FROM professional_profiles pp
                    JOIN monitoring_professionals mp
                      ON mp.professional_profile_id = pp.id
                    JOIN monitoring_plans plan
                      ON plan.id = mp.monitoring_plan_id
                    WHERE pp.user_id = app_private.current_user_id()
                      AND pp.active IS TRUE
                      AND mp.active IS TRUE
                      AND plan.active IS TRUE
                      AND plan.patient_id = anamneses.user_id
                )
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS anamneses_insert ON anamneses")
    op.execute("DROP POLICY IF EXISTS anamneses_update ON anamneses")
    op.execute(
        """
        CREATE POLICY anamneses_insert ON anamneses FOR INSERT WITH CHECK (
            app_private.service_context() OR app_private.can_access_patient(user_id)
        )
        """
    )
    op.execute(
        """
        CREATE POLICY anamneses_update ON anamneses FOR UPDATE
            USING (app_private.service_context() OR app_private.can_access_patient(user_id))
            WITH CHECK (app_private.service_context() OR app_private.can_access_patient(user_id))
        """
    )
    op.execute("DROP FUNCTION IF EXISTS app_private.patient_has_active_professional_plan(integer)")
