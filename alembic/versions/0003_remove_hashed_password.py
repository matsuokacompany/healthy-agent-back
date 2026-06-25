"""remove hashed password from users

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-25
"""

from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS hashed_password")


def downgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR")
