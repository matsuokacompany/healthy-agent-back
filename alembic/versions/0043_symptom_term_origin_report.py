"""Origin-report pointer on daily_report_symptom_terms, so a purely
referential follow-up ("mesma dor, mesmo lugar") can carry forward the
detailed description from where the symptom was first actually described --
for both the grouped patient/professional view and the AI-facing report
text -- instead of losing that detail behind a short clinical term or an
uninformative "mesma dor" repeated on every later day.

Revision ID: 0043
Revises: 0042
"""

from alembic import op
import sqlalchemy as sa


revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_report_symptom_terms",
        sa.Column(
            "origin_report_id",
            sa.Integer(),
            sa.ForeignKey("daily_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_daily_report_symptom_terms_origin_report_id",
        "daily_report_symptom_terms",
        ["origin_report_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_report_symptom_terms_origin_report_id", table_name="daily_report_symptom_terms")
    op.drop_column("daily_report_symptom_terms", "origin_report_id")
