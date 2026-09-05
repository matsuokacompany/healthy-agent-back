from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.billing_plans import get_professional_plan
from app.models.models import MonitoringPlan, MonitoringProfessional, ProfessionalProfile, Subscription
from app.services.payment_service import subscription_grants_access

# Applied to a professional with billing access but no chosen plan_id yet
# (paid trial before checkout) -- the most conservative (smallest) tier, so
# margin is protected by default rather than by omission.
DEFAULT_PROFESSIONAL_PATIENT_CAP = 10


def _linked_patient_ids(db: Session, professional_profile_id: int) -> list[int]:
    rows = (
        db.query(MonitoringPlan.patient_id)
        .join(MonitoringProfessional, MonitoringProfessional.monitoring_plan_id == MonitoringPlan.id)
        .filter(
            MonitoringProfessional.professional_profile_id == professional_profile_id,
            MonitoringProfessional.active.is_(True),
            MonitoringPlan.active.is_(True),
        )
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


def patient_has_own_subscription(db: Session, patient_id: int) -> bool:
    """Whether this patient already pays for their own self-service access.

    Such a patient doesn't count against the professional's active-patient
    cap -- they're already paying for the assistant themselves, so linking
    them costs the professional nothing.
    """
    subscription = db.query(Subscription).filter(Subscription.user_id == patient_id).first()
    return subscription_grants_access(subscription)


def count_active_patients(db: Session, professional_profile_id: int) -> int:
    patient_ids = _linked_patient_ids(db, professional_profile_id)
    return sum(1 for patient_id in patient_ids if not patient_has_own_subscription(db, patient_id))


def resolve_patient_cap(db: Session, profile: ProfessionalProfile) -> int | None:
    """The active-patient cap for this professional, or None if uncapped
    (grandfathered inside their `free_until` grace period)."""
    if profile.free_until is not None and datetime.now(timezone.utc).date() <= profile.free_until:
        return None
    subscription = db.query(Subscription).filter(Subscription.user_id == profile.user_id).first()
    plan = get_professional_plan(subscription.plan_id) if subscription and subscription.plan_id else None
    return plan.max_patients if plan and plan.max_patients else DEFAULT_PROFESSIONAL_PATIENT_CAP


def require_patient_cap(db: Session, profile: ProfessionalProfile | None) -> None:
    """Blocks adding one more active patient once a professional is at their
    plan tier's cap. None profile means the caller is an admin acting
    without a professional profile -- always passes, same as
    ProfessionalService._require_billing_access.
    """
    if profile is None:
        return
    cap = resolve_patient_cap(db, profile)
    if cap is None:
        return
    active_count = count_active_patients(db, profile.id)
    if active_count >= cap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "PROFESSIONAL_PATIENT_CAP_REACHED", "cap": cap, "active_patients": active_count},
        )
