"""Add users.street/neighborhood/zip_code/health_plan (address and
health-insurance-plan fields shown on the patient profile page, previously
never persisted anywhere).

Revision ID: 0045
Revises: 0044
"""

from alembic import op
import sqlalchemy as sa


revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("street", sa.String(), nullable=True))
    op.add_column("users", sa.Column("neighborhood", sa.String(), nullable=True))
    op.add_column("users", sa.Column("zip_code", sa.String(), nullable=True))
    op.add_column("users", sa.Column("health_plan", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "health_plan")
    op.drop_column("users", "zip_code")
    op.drop_column("users", "neighborhood")
    op.drop_column("users", "street")
