"""Self-service (B2C) monitoring and professional subscription plan catalogs.

Plans are driven entirely by ASAAS_*_PRICE_CENTS settings — a plan only
appears once its price is explicitly configured (see the "no default"
comment in app/core/config.py), so nothing is ever offered or charged at a
guessed price.
"""

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass(frozen=True)
class SelfMonitoringPlan:
    id: str
    label: str
    cycle: str  # Asaas subscription "cycle" value
    months: int
    price_cents: int
    # Max simultaneously active patients for a professional plan tier; None
    # for every self-monitoring plan (a patient's own subscription has no
    # such concept) and also None for a professional plan with no cap wired
    # up yet.
    max_patients: Optional[int] = None


def _build_catalog(entries) -> list[SelfMonitoringPlan]:
    return [
        SelfMonitoringPlan(id=plan_id, label=label, cycle=cycle, months=months, price_cents=price_cents, max_patients=max_patients)
        for plan_id, label, cycle, months, price_cents, max_patients in entries
        if price_cents
    ]


def get_self_monitoring_plans() -> list[SelfMonitoringPlan]:
    return _build_catalog((
        ("monthly", "Mensal", "MONTHLY", 1, settings.ASAAS_SELF_MONITORING_PRICE_CENTS, None),
        ("semiannual", "Semestral", "SEMIANNUALLY", 6, settings.ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS, None),
        ("annual", "Anual", "YEARLY", 12, settings.ASAAS_SELF_MONITORING_ANNUAL_PRICE_CENTS, None),
    ))


def get_self_monitoring_plan(plan_id: str) -> Optional[SelfMonitoringPlan]:
    return next((plan for plan in get_self_monitoring_plans() if plan.id == plan_id), None)


# Professional plan ids for the base (10-patient) tier are deliberately left
# unprefixed ("monthly"/"semiannual"/"annual") — they predate the tier
# concept, and existing paying subscribers already have these bare ids
# stored on Subscription.plan_id. Renaming them would orphan those rows.
def get_professional_plans() -> list[SelfMonitoringPlan]:
    return _build_catalog((
        ("monthly", "Até 10 pacientes · Mensal", "MONTHLY", 1, settings.ASAAS_PROFESSIONAL_MONTHLY_PRICE_CENTS, 10),
        ("semiannual", "Até 10 pacientes · Semestral", "SEMIANNUALLY", 6, settings.ASAAS_PROFESSIONAL_SEMIANNUAL_PRICE_CENTS, 10),
        ("annual", "Até 10 pacientes · Anual", "YEARLY", 12, settings.ASAAS_PROFESSIONAL_ANNUAL_PRICE_CENTS, 10),
        ("tier25_monthly", "Até 25 pacientes · Mensal", "MONTHLY", 1, settings.ASAAS_PROFESSIONAL_TIER25_MONTHLY_PRICE_CENTS, 25),
        ("tier25_semiannual", "Até 25 pacientes · Semestral", "SEMIANNUALLY", 6, settings.ASAAS_PROFESSIONAL_TIER25_SEMIANNUAL_PRICE_CENTS, 25),
        ("tier25_annual", "Até 25 pacientes · Anual", "YEARLY", 12, settings.ASAAS_PROFESSIONAL_TIER25_ANNUAL_PRICE_CENTS, 25),
        ("tier50_monthly", "Até 50 pacientes · Mensal", "MONTHLY", 1, settings.ASAAS_PROFESSIONAL_TIER50_MONTHLY_PRICE_CENTS, 50),
        ("tier50_semiannual", "Até 50 pacientes · Semestral", "SEMIANNUALLY", 6, settings.ASAAS_PROFESSIONAL_TIER50_SEMIANNUAL_PRICE_CENTS, 50),
        ("tier50_annual", "Até 50 pacientes · Anual", "YEARLY", 12, settings.ASAAS_PROFESSIONAL_TIER50_ANNUAL_PRICE_CENTS, 50),
    ))


def get_professional_plan(plan_id: str) -> Optional[SelfMonitoringPlan]:
    return next((plan for plan in get_professional_plans() if plan.id == plan_id), None)
