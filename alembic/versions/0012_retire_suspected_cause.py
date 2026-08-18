"""Retire patient-reported suspected causes and erase legacy values.

Revision ID: 0012
Revises: 0011
"""

from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the columns temporarily for a backwards-compatible rolling deploy,
    # but enforce data minimization by deleting both representations. The new
    # application no longer accepts or returns this field.
    op.execute(
        """
        UPDATE daily_reports
        SET suspected_cause = NULL,
            suspected_cause_encryption_envelope = NULL
        WHERE suspected_cause IS NOT NULL
           OR suspected_cause_encryption_envelope IS NOT NULL
        """
    )


def downgrade() -> None:
    # Erased clinical data cannot and should not be reconstructed.
    pass
