"""add report_date to daily_reports and update uniqueness

Revision ID: 8f3c1a4b2d10
Revises: 3ddf7c59e2fc
Create Date: 2026-04-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3c1a4b2d10'
down_revision: Union[str, None] = '3ddf7c59e2fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_reports', sa.Column('report_date', sa.Date(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE daily_reports
            SET report_date = DATE(created_at)
            WHERE report_date IS NULL
            """
        )
    )

    op.alter_column('daily_reports', 'report_date', existing_type=sa.Date(), nullable=False)

    op.drop_constraint('uq_user_check_day', 'daily_reports', type_='unique')
    op.create_unique_constraint(
        'uq_user_report_date_check',
        'daily_reports',
        ['user_id', 'report_date', 'check_type'],
    )
    op.create_index(op.f('ix_daily_reports_report_date'), 'daily_reports', ['report_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_daily_reports_report_date'), table_name='daily_reports')

    op.drop_constraint('uq_user_report_date_check', 'daily_reports', type_='unique')
    op.create_unique_constraint(
        'uq_user_check_day',
        'daily_reports',
        ['user_id', 'check_type', 'created_at'],
    )

    op.drop_column('daily_reports', 'report_date')
