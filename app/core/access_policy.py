from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import is_admin, require_role
from app.models.models import (
    MonitoringPlan,
    MonitoringProfessional,
    ProfessionalProfile,
    RoleNameEnum,
    User,
)


class AccessPolicy:
    """Server-side authorization for resources scoped to a patient."""

    def __init__(self, db: Session, actor: User):
        self.db = db
        self.actor = actor

    def require_self(self, target_user_id: int) -> None:
        if self.actor.id != target_user_id and not is_admin(self.actor):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    def require_active_professional_profile(self) -> ProfessionalProfile | None:
        if is_admin(self.actor):
            return None
        require_role(self.actor, RoleNameEnum.PROFESSIONAL)
        profile = (
            self.db.query(ProfessionalProfile)
            .filter(
                ProfessionalProfile.user_id == self.actor.id,
                ProfessionalProfile.active.is_(True),
            )
            .first()
        )
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Active professional profile required",
            )
        return profile

    def require_patient_read(self, patient_id: int) -> User:
        patient = self.db.query(User).filter(User.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        if is_admin(self.actor) or self.actor.id == patient_id:
            return patient

        profile = self.require_active_professional_profile()
        link = (
            self.db.query(MonitoringProfessional.id)
            .join(MonitoringPlan, MonitoringPlan.id == MonitoringProfessional.monitoring_plan_id)
            .filter(
                MonitoringPlan.patient_id == patient_id,
                MonitoringPlan.active.is_(True),
                MonitoringProfessional.professional_profile_id == profile.id,
                MonitoringProfessional.active.is_(True),
            )
            .first()
        )
        if not link:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this patient",
            )
        return patient

    def require_professional_patient_read(self, patient_id: int) -> User:
        if not is_admin(self.actor):
            require_role(self.actor, RoleNameEnum.PROFESSIONAL)
        return self.require_patient_read(patient_id)
