"""add user role for access context

Revision ID: 9c8b1f2d4a7e
Revises: 3ddf7c59e2fc
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c8b1f2d4a7e"
down_revision: Union[str, None] = "3ddf7c59e2fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(), server_default="patient", nullable=False),
    )
    op.execute("UPDATE users SET role = 'professional' WHERE is_admin IS TRUE")
    op.execute(
        "UPDATE users SET role = 'super_admin' "
        "WHERE id = 1 AND email = 'matsuokacompany@gmail.com'"
    )


def downgrade() -> None:
    op.drop_column("users", "role")
