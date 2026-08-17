"""add row-level security policies

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-17
"""

from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


RLS_TABLES = (
    "users",
    "roles",
    "user_roles",
    "professional_profiles",
    "monitoring_plans",
    "monitoring_professionals",
    "anamneses",
    "daily_reports",
    "ai_report_cache",
    "whatsapp_messages",
)


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthy_agent_api') THEN
                CREATE ROLE healthy_agent_api NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
            END IF;
            EXECUTE format('GRANT healthy_agent_api TO %I', current_user);
        END
        $$
        """
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS app_private")
    op.execute("REVOKE CREATE ON SCHEMA app_private FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA app_private TO PUBLIC")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.service_context()
        RETURNS boolean
        LANGUAGE sql STABLE
        AS $$
            SELECT COALESCE(current_setting('app.service_context', true), '') <> ''
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.current_supabase_user_id()
        RETURNS uuid
        LANGUAGE sql STABLE
        AS $$
            SELECT NULLIF(current_setting('app.supabase_user_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.current_user_id()
        RETURNS integer
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT id
            FROM users
            WHERE supabase_user_id = app_private.current_supabase_user_id()
            LIMIT 1
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.current_user_has_role(target_role text)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = app_private.current_user_id()
                  AND r.name = target_role
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.current_user_is_admin()
        RETURNS boolean
        LANGUAGE sql STABLE
        AS $$
            SELECT app_private.current_user_has_role('admin')
                OR app_private.current_user_has_role('super_admin')
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.can_access_patient(target_patient_id integer)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT
                target_patient_id = app_private.current_user_id()
                OR app_private.current_user_is_admin()
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
                      AND plan.patient_id = target_patient_id
                )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_private.can_access_professional(target_profile_id integer)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT
                app_private.current_user_is_admin()
                OR EXISTS (
                    SELECT 1 FROM professional_profiles pp
                    WHERE pp.id = target_profile_id
                      AND pp.user_id = app_private.current_user_id()
                )
                OR EXISTS (
                    SELECT 1
                    FROM monitoring_professionals mp
                    JOIN monitoring_plans plan ON plan.id = mp.monitoring_plan_id
                    WHERE mp.professional_profile_id = target_profile_id
                      AND mp.active IS TRUE
                      AND plan.active IS TRUE
                      AND plan.patient_id = app_private.current_user_id()
                )
        $$
        """
    )

    op.execute(
        """
        CREATE POLICY users_select ON users FOR SELECT USING (
            app_private.service_context()
            OR app_private.can_access_patient(id)
            OR (
                supabase_user_id IS NULL
                AND email = NULLIF(current_setting('app.user_email', true), '')
            )
        );
        CREATE POLICY users_insert ON users FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR supabase_user_id = app_private.current_supabase_user_id()
        );
        CREATE POLICY users_update ON users FOR UPDATE
            USING (
                app_private.service_context()
                OR id = app_private.current_user_id()
                OR app_private.current_user_is_admin()
                OR (
                    supabase_user_id IS NULL
                    AND email = NULLIF(current_setting('app.user_email', true), '')
                )
            )
            WITH CHECK (
                app_private.service_context()
                OR id = app_private.current_user_id()
                OR app_private.current_user_is_admin()
                OR supabase_user_id = app_private.current_supabase_user_id()
            );
        CREATE POLICY users_delete ON users FOR DELETE USING (
            app_private.service_context() OR id = app_private.current_user_id() OR app_private.current_user_is_admin()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY roles_select ON roles FOR SELECT USING (
            app_private.service_context() OR app_private.current_supabase_user_id() IS NOT NULL
        );
        CREATE POLICY roles_write ON roles FOR ALL
            USING (app_private.service_context() OR app_private.current_user_is_admin())
            WITH CHECK (app_private.service_context() OR app_private.current_user_is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY user_roles_select ON user_roles FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(user_id)
        );
        CREATE POLICY user_roles_insert ON user_roles FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR (
                user_id = app_private.current_user_id()
                AND EXISTS (SELECT 1 FROM roles r WHERE r.id = role_id AND r.name = 'patient')
            )
        );
        CREATE POLICY user_roles_update ON user_roles FOR UPDATE
            USING (app_private.service_context() OR app_private.current_user_is_admin())
            WITH CHECK (app_private.service_context() OR app_private.current_user_is_admin());
        CREATE POLICY user_roles_delete ON user_roles FOR DELETE USING (
            app_private.service_context() OR app_private.current_user_is_admin()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY professional_profiles_select ON professional_profiles FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_professional(id)
        );
        CREATE POLICY professional_profiles_insert ON professional_profiles FOR INSERT WITH CHECK (
            app_private.service_context() OR app_private.current_user_is_admin()
        );
        CREATE POLICY professional_profiles_update ON professional_profiles FOR UPDATE
            USING (app_private.service_context() OR user_id = app_private.current_user_id() OR app_private.current_user_is_admin())
            WITH CHECK (app_private.service_context() OR user_id = app_private.current_user_id() OR app_private.current_user_is_admin());
        CREATE POLICY professional_profiles_delete ON professional_profiles FOR DELETE USING (
            app_private.service_context() OR user_id = app_private.current_user_id() OR app_private.current_user_is_admin()
        )
        """
    )
    op.execute(
        """
        CREATE POLICY monitoring_plans_select ON monitoring_plans FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(patient_id)
        );
        CREATE POLICY monitoring_plans_insert ON monitoring_plans FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR app_private.current_user_has_role('professional')
        );
        CREATE POLICY monitoring_plans_update ON monitoring_plans FOR UPDATE
            USING (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR (app_private.current_user_has_role('professional') AND app_private.can_access_patient(patient_id))
            )
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR (app_private.current_user_has_role('professional') AND app_private.can_access_patient(patient_id))
            );
        CREATE POLICY monitoring_plans_delete ON monitoring_plans FOR DELETE USING (
            app_private.service_context() OR app_private.current_user_is_admin()
        )
        """
    )
    op.execute(
        """
        CREATE POLICY monitoring_professionals_select ON monitoring_professionals FOR SELECT USING (
            app_private.service_context()
            OR EXISTS (
                SELECT 1 FROM monitoring_plans plan
                WHERE plan.id = monitoring_plan_id
                  AND app_private.can_access_patient(plan.patient_id)
            )
        );
        CREATE POLICY monitoring_professionals_insert ON monitoring_professionals FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR EXISTS (
                SELECT 1 FROM professional_profiles pp
                WHERE pp.id = professional_profile_id
                  AND pp.user_id = app_private.current_user_id()
                  AND pp.active IS TRUE
            )
        );
        CREATE POLICY monitoring_professionals_update ON monitoring_professionals FOR UPDATE
            USING (app_private.service_context() OR app_private.current_user_is_admin() OR app_private.can_access_professional(professional_profile_id))
            WITH CHECK (app_private.service_context() OR app_private.current_user_is_admin() OR app_private.can_access_professional(professional_profile_id));
        CREATE POLICY monitoring_professionals_delete ON monitoring_professionals FOR DELETE USING (
            app_private.service_context() OR app_private.current_user_is_admin()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY anamneses_select ON anamneses FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(user_id)
        );
        CREATE POLICY anamneses_insert ON anamneses FOR INSERT WITH CHECK (
            app_private.service_context() OR app_private.can_access_patient(user_id)
        );
        CREATE POLICY anamneses_update ON anamneses FOR UPDATE
            USING (app_private.service_context() OR app_private.can_access_patient(user_id))
            WITH CHECK (app_private.service_context() OR app_private.can_access_patient(user_id));
        CREATE POLICY anamneses_delete ON anamneses FOR DELETE USING (
            app_private.service_context() OR app_private.can_access_patient(user_id)
        )
        """
    )
    op.execute(
        """
        CREATE POLICY daily_reports_select ON daily_reports FOR SELECT USING (
            app_private.service_context() OR app_private.can_access_patient(user_id)
        );
        CREATE POLICY daily_reports_insert ON daily_reports FOR INSERT WITH CHECK (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR user_id = app_private.current_user_id()
        );
        CREATE POLICY daily_reports_update ON daily_reports FOR UPDATE
            USING (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR user_id = app_private.current_user_id()
            )
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR user_id = app_private.current_user_id()
            );
        CREATE POLICY daily_reports_delete ON daily_reports FOR DELETE USING (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR user_id = app_private.current_user_id()
        )
        """
    )

    op.execute(
        """
        CREATE POLICY ai_report_cache_select ON ai_report_cache FOR SELECT USING (
            app_private.service_context()
            OR app_private.current_user_is_admin()
            OR (
                app_private.current_user_has_role('professional')
                AND app_private.can_access_patient(patient_id)
            )
        );
        CREATE POLICY ai_report_cache_write ON ai_report_cache FOR ALL
            USING (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR (
                    app_private.current_user_has_role('professional')
                    AND app_private.can_access_patient(patient_id)
                )
            )
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR (
                    app_private.current_user_has_role('professional')
                    AND app_private.can_access_patient(patient_id)
                )
            )
        """
    )
    op.execute(
        """
        CREATE POLICY whatsapp_messages_service ON whatsapp_messages FOR ALL
            USING (app_private.service_context())
            WITH CHECK (app_private.service_context())
        """
    )

    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')

    op.execute("GRANT USAGE ON SCHEMA public, app_private TO healthy_agent_api")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO healthy_agent_api")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO healthy_agent_api")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app_private TO healthy_agent_api")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO healthy_agent_api")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO healthy_agent_api")


def downgrade():
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM healthy_agent_api")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM healthy_agent_api")
    for table in reversed(RLS_TABLES):
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    policy_names = {
        "users": ("users_select", "users_insert", "users_update", "users_delete"),
        "roles": ("roles_select", "roles_write"),
        "user_roles": ("user_roles_select", "user_roles_insert", "user_roles_update", "user_roles_delete"),
        "professional_profiles": (
            "professional_profiles_select",
            "professional_profiles_insert",
            "professional_profiles_update",
            "professional_profiles_delete",
        ),
        "monitoring_plans": (
            "monitoring_plans_select",
            "monitoring_plans_insert",
            "monitoring_plans_update",
            "monitoring_plans_delete",
        ),
        "monitoring_professionals": (
            "monitoring_professionals_select",
            "monitoring_professionals_insert",
            "monitoring_professionals_update",
            "monitoring_professionals_delete",
        ),
        "anamneses": ("anamneses_select", "anamneses_insert", "anamneses_update", "anamneses_delete"),
        "daily_reports": ("daily_reports_select", "daily_reports_insert", "daily_reports_update", "daily_reports_delete"),
        "ai_report_cache": ("ai_report_cache_select", "ai_report_cache_write"),
        "whatsapp_messages": ("whatsapp_messages_service",),
    }
    for table, policies in policy_names.items():
        for policy in policies:
            op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')

    for function in (
        "can_access_professional(integer)",
        "can_access_patient(integer)",
        "current_user_is_admin()",
        "current_user_has_role(text)",
        "current_user_id()",
        "current_supabase_user_id()",
        "service_context()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS app_private.{function}")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM healthy_agent_api")
    op.execute("REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM healthy_agent_api")
    op.execute("REVOKE USAGE ON SCHEMA public, app_private FROM healthy_agent_api")
    op.execute("DROP SCHEMA IF EXISTS app_private")
