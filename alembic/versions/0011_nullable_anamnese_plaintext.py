"""allow ciphertext-only anamneses

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("anamneses", "info", existing_type=sa.Text(), nullable=True)


def downgrade():
    op.alter_column("anamneses", "info", existing_type=sa.Text(), nullable=False)
