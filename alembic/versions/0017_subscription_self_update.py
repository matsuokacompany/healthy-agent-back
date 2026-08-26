"""Allow a patient to update their own subscription row (billing details only).

Revision ID: 0017
Revises: 0016
"""

from alembic import op


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # subscriptions_update (0015) only allowed service_context/admin to UPDATE,
    # but PaymentService.start_checkout() updates the patient's own row
    # (provider_customer_id, provider_subscription_id) under the patient's own
    # identity context — that UPDATE was silently rejected by RLS (0 rows
    # matched), surfacing as a 500 on POST /api/billing/subscription.
    op.execute("DROP POLICY IF EXISTS subscriptions_update ON subscriptions")
    op.execute(
        """
        CREATE POLICY subscriptions_update ON subscriptions FOR UPDATE
            USING (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR user_id = app_private.current_user_id()
            )
            WITH CHECK (
                app_private.service_context()
                OR app_private.current_user_is_admin()
                OR user_id = app_private.current_user_id()
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS subscriptions_update ON subscriptions")
    op.execute(
        """
        CREATE POLICY subscriptions_update ON subscriptions FOR UPDATE
            USING (app_private.service_context() OR app_private.current_user_is_admin())
            WITH CHECK (app_private.service_context() OR app_private.current_user_is_admin())
        """
    )
