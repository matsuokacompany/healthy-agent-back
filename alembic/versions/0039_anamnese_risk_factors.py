"""Structured risk-factor checklist on Anamnese, reviewed with a healthcare
professional -- see app/services/red_flag_symptoms.py's
ANAMNESE_RISK_FACTORS and CONTEXTUAL_RISK_RULES. Feeds the CONTEXTUAL tier
of red-flag symptom detection: an otherwise-routine symptom (e.g. mild
shortness of breath) becomes red-flag-worthy given a matching risk factor
here (e.g. a recent surgery or a history of thrombosis).

Plain (unencrypted) booleans, same as the other clinical flags on
DailyReport -- not free text, so no envelope-encryption columns needed.

Revision ID: 0039
Revises: 0038
"""

from alembic import op
import sqlalchemy as sa


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

RISK_FACTOR_COLUMNS = (
    "risk_heart_disease",
    "risk_prior_heart_attack",
    "risk_prior_stroke_or_tia",
    "risk_asthma_or_copd",
    "risk_heart_failure",
    "risk_diabetes",
    "risk_anticoagulant_use",
    "risk_immunosuppression",
    "risk_pregnancy_or_postpartum",
    "risk_active_cancer",
    "risk_prior_thrombosis_or_embolism",
    "risk_recent_surgery_or_immobilization",
    "risk_epilepsy",
)


def upgrade() -> None:
    for column_name in RISK_FACTOR_COLUMNS:
        op.add_column("anamneses", sa.Column(column_name, sa.Boolean(), nullable=True))


def downgrade() -> None:
    for column_name in reversed(RISK_FACTOR_COLUMNS):
        op.drop_column("anamneses", column_name)
