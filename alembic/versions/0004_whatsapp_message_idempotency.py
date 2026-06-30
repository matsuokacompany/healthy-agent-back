"""whatsapp message idempotency

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("message_id", sa.String, nullable=False),
        sa.Column("channel", sa.String, nullable=False, server_default="whatsapp"),
        sa.Column("external_user_id", sa.String, nullable=False),
        sa.Column("normalized_user_id", sa.String, nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="PROCESSING"),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("message_id", name="uq_whatsapp_messages_message_id"),
    )
    op.create_index("ix_whatsapp_messages_user_id", "whatsapp_messages", ["user_id"], unique=False)
    op.create_index("ix_whatsapp_messages_status", "whatsapp_messages", ["status"], unique=False)


def downgrade():
    op.drop_index("ix_whatsapp_messages_status", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_user_id", table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")
