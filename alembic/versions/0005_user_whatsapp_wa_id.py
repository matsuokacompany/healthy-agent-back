"""user whatsapp wa id

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("whatsapp_wa_id", sa.String(), nullable=True))
    op.create_index("ix_users_whatsapp_wa_id", "users", ["whatsapp_wa_id"], unique=True)


def downgrade():
    op.drop_index("ix_users_whatsapp_wa_id", table_name="users")
    op.drop_column("users", "whatsapp_wa_id")
