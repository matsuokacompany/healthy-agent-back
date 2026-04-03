"""add pending report fields to users and had_symptoms to daily_reports

Revision ID: c6a9f1b4d2e3
Revises: 8f3c1a4b2d10
Create Date: 2026-04-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6a9f1b4d2e3'
down_revision: Union[str, None] = '8f3c1a4b2d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('pending_check_type', sa.Enum('MORNING', 'NIGHT', name='checktypeenum'), nullable=True))
    op.add_column('users', sa.Column('pending_report_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('pending_prompt_sent_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('daily_reports', sa.Column('had_symptoms', sa.Boolean(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE daily_reports
            SET had_symptoms = CASE
                WHEN symptom_description IS NULL OR TRIM(symptom_description) = '' THEN FALSE
                ELSE TRUE
            END
            WHERE had_symptoms IS NULL
            """
        )
    )

    op.alter_column('daily_reports', 'had_symptoms', existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    op.drop_column('daily_reports', 'had_symptoms')

    op.drop_column('users', 'pending_prompt_sent_at')
    op.drop_column('users', 'pending_report_date')
    op.drop_column('users', 'pending_check_type')
