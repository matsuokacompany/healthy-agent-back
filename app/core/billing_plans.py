"""Self-service (B2C) monitoring subscription plan catalog.

Plans are driven entirely by ASAAS_SELF_MONITORING_*_PRICE_CENTS settings — a
plan only appears once its price is explicitly configured (see the "no
default" comment in app/core/config.py), so nothing is ever offered or
charged at a guessed price.
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


def _build_catalog(entries) -> list[SelfMonitoringPlan]:
    return [
        SelfMonitoringPlan(id=plan_id, label=label, cycle=cycle, months=months, price_cents=price_cents)
        for plan_id, label, cycle, months, price_cents in entries
        if price_cents
    ]


def get_self_monitoring_plans() -> list[SelfMonitoringPlan]:
    return _build_catalog((
        ("monthly", "Mensal", "MONTHLY", 1, settings.ASAAS_SELF_MONITORING_PRICE_CENTS),
        ("semiannual", "Semestral", "SEMIANNUALLY", 6, settings.ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS),
        ("annual", "Anual", "YEARLY", 12, settings.ASAAS_SELF_MONITORING_ANNUAL_PRICE_CENTS),
    ))


def get_self_monitoring_plan(plan_id: str) -> Optional[SelfMonitoringPlan]:
    return next((plan for plan in get_self_monitoring_plans() if plan.id == plan_id), None)


def get_professional_plans() -> list[SelfMonitoringPlan]:
    return _build_catalog((
        ("monthly", "Mensal", "MONTHLY", 1, settings.ASAAS_PROFESSIONAL_MONTHLY_PRICE_CENTS),
        ("semiannual", "Semestral", "SEMIANNUALLY", 6, settings.ASAAS_PROFESSIONAL_SEMIANNUAL_PRICE_CENTS),
        ("annual", "Anual", "YEARLY", 12, settings.ASAAS_PROFESSIONAL_ANNUAL_PRICE_CENTS),
    ))


def get_professional_plan(plan_id: str) -> Optional[SelfMonitoringPlan]:
    return next((plan for plan in get_professional_plans() if plan.id == plan_id), None)
