from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import MonitoringPlan, MonitoringProfessional, ProfessionalProfile, User
from app.models.schemas import (
    MonitoringPlanCreate,
    MonitoringPlanUpdate,
    MonitoringProfessionalCreate,
    MonitoringProfessionalUpdate,
    ProfessionalProfileCreate,
    ProfessionalProfileUpdate,
)


class ProfessionalProfileService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: ProfessionalProfileCreate) -> ProfessionalProfile:
        user = self.db.query(User).filter(User.id == payload.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if self.db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == payload.user_id).first():
            raise HTTPException(status_code=409, detail="Professional profile already exists")
        profile = ProfessionalProfile(**payload.model_dump())
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update(self, profile_id: int, payload: ProfessionalProfileUpdate) -> ProfessionalProfile:
        profile = self.db.query(ProfessionalProfile).filter(ProfessionalProfile.id == profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Professional profile not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        self.db.commit()
        self.db.refresh(profile)
        return profile


class MonitoringPlanService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: MonitoringPlanCreate) -> MonitoringPlan:
        patient = self.db.query(User).filter(User.id == payload.patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        self._validate_dates(payload.start_date, payload.end_date)
        plan = MonitoringPlan(**payload.model_dump())
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def update(self, plan_id: int, payload: MonitoringPlanUpdate) -> MonitoringPlan:
        plan = self.get(plan_id)
        data = payload.model_dump(exclude_unset=True)
        start_date = data.get("start_date", plan.start_date)
        end_date = data.get("end_date", plan.end_date)
        self._validate_dates(start_date, end_date)
        for field, value in data.items():
            setattr(plan, field, value)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def get(self, plan_id: int) -> MonitoringPlan:
        plan = self.db.query(MonitoringPlan).filter(MonitoringPlan.id == plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Monitoring plan not found")
        return plan

    def list_for_patient(self, patient_id: int) -> list[MonitoringPlan]:
        return self.db.query(MonitoringPlan).filter(MonitoringPlan.patient_id == patient_id).all()

    def add_professional(self, plan_id: int, payload: MonitoringProfessionalCreate) -> MonitoringProfessional:
        plan = self.get(plan_id)
        professional = (
            self.db.query(ProfessionalProfile)
            .filter(ProfessionalProfile.id == payload.professional_profile_id, ProfessionalProfile.active.is_(True))
            .first()
        )
        if not professional:
            raise HTTPException(status_code=404, detail="Active professional profile not found")
        existing = (
            self.db.query(MonitoringProfessional)
            .filter(
                MonitoringProfessional.monitoring_plan_id == plan.id,
                MonitoringProfessional.professional_profile_id == professional.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Professional already linked to plan")
        link = MonitoringProfessional(
            monitoring_plan_id=plan.id,
            professional_profile_id=professional.id,
            role=payload.role,
            active=True,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def update_professional(self, link_id: int, payload: MonitoringProfessionalUpdate) -> MonitoringProfessional:
        link = self.db.query(MonitoringProfessional).filter(MonitoringProfessional.id == link_id).first()
        if not link:
            raise HTTPException(status_code=404, detail="Monitoring professional link not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(link, field, value)
        self.db.commit()
        self.db.refresh(link)
        return link

    @staticmethod
    def _validate_dates(start_date: date | None, end_date: date | None) -> None:
        if start_date and end_date and end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be greater than or equal to start_date",
            )
