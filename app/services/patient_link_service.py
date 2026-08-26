from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.email import send_email
from app.db.security_context import set_database_service_context
from app.models.models import (
    MonitoringPlan,
    MonitoringPlanOriginEnum,
    MonitoringProfessional,
    PatientLinkRequest,
    PatientLinkRequestStatusEnum,
    ProfessionalProfile,
    RoleNameEnum,
    Subscription,
    SubscriptionStatusEnum,
    User,
)

LINK_REQUEST_EXPIRY_DAYS = 7

# Granted to the professional once, on accept, when the patient still has a
# paying self-service subscription — instead of cancelling that subscription,
# it lets the professional generate one AI report for this patient ahead of
# the normal monthly cooldown (see find_link_with_bonus_credit below).
BONUS_REPORT_CREDITS_ON_LINK = 1


def find_link_with_bonus_credit(db: Session, *, patient_id: int, professional_user_id: int) -> MonitoringProfessional | None:
    """The active MonitoringProfessional link between this professional and
    patient that still has an unused bonus report credit, if any."""
    return (
        db.query(MonitoringProfessional)
        .join(MonitoringPlan, MonitoringPlan.id == MonitoringProfessional.monitoring_plan_id)
        .join(ProfessionalProfile, ProfessionalProfile.id == MonitoringProfessional.professional_profile_id)
        .filter(
            MonitoringPlan.patient_id == patient_id,
            MonitoringPlan.active.is_(True),
            MonitoringProfessional.active.is_(True),
            ProfessionalProfile.user_id == professional_user_id,
            MonitoringProfessional.bonus_report_credits > 0,
        )
        .first()
    )


class PatientLinkService:
    """Lets a professional request to become responsible for an existing
    patient account (e.g. one that self-registered) instead of silently
    taking it over on a duplicate-email conflict — the patient must accept.
    """

    def __init__(self, db: Session):
        self.db = db

    def _require_active_professional_profile(self, current_user: User) -> ProfessionalProfile:
        profile = (
            self.db.query(ProfessionalProfile)
            .filter(ProfessionalProfile.user_id == current_user.id, ProfessionalProfile.active.is_(True))
            .first()
        )
        if not profile:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active professional profile required")
        return profile

    @staticmethod
    def _has_active_professional_link(db: Session, patient_id: int) -> bool:
        return (
            db.query(MonitoringProfessional.id)
            .join(MonitoringPlan, MonitoringPlan.id == MonitoringProfessional.monitoring_plan_id)
            .filter(
                MonitoringPlan.patient_id == patient_id,
                MonitoringPlan.active.is_(True),
                MonitoringProfessional.active.is_(True),
            )
            .first()
            is not None
        )

    def create_request(self, current_user: User, email: str) -> dict:
        profile = self._require_active_professional_profile(current_user)

        patient = self.db.query(User).filter(User.email == email).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No patient account found for this email")
        if RoleNameEnum.PATIENT.value not in patient.roles:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account is not a patient")
        if self._has_active_professional_link(self.db, patient.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Patient is already linked to a professional")

        now = datetime.now(timezone.utc)
        existing_pending = (
            self.db.query(PatientLinkRequest)
            .filter(
                PatientLinkRequest.professional_profile_id == profile.id,
                PatientLinkRequest.patient_user_id == patient.id,
                PatientLinkRequest.status == PatientLinkRequestStatusEnum.PENDING.value,
                PatientLinkRequest.expires_at > now,
            )
            .first()
        )
        if existing_pending:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending request already exists for this patient")

        set_database_service_context(self.db, "patient_link_request")
        link_request = PatientLinkRequest(
            professional_profile_id=profile.id,
            patient_user_id=patient.id,
            status=PatientLinkRequestStatusEnum.PENDING.value,
            expires_at=now + timedelta(days=LINK_REQUEST_EXPIRY_DAYS),
        )
        self.db.add(link_request)
        self.db.commit()
        self.db.refresh(link_request)

        send_email(
            to=patient.email,
            subject="Pedido de vínculo com um profissional na Julha",
            body=(
                f"Olá, {patient.name}!\n\n"
                f"{current_user.name} pediu para acompanhar seu monitoramento na Julha.\n\n"
                "Entre na plataforma para aceitar ou recusar esse pedido — nada muda até você decidir.\n\n"
                "Equipe Julha"
            ),
        )

        return self._to_sent_dict(link_request, patient)

    def list_sent_requests(self, current_user: User) -> list[dict]:
        profile = self._require_active_professional_profile(current_user)
        rows = (
            self.db.query(PatientLinkRequest, User)
            .join(User, User.id == PatientLinkRequest.patient_user_id)
            .filter(PatientLinkRequest.professional_profile_id == profile.id)
            .order_by(PatientLinkRequest.created_at.desc())
            .all()
        )
        return [self._to_sent_dict(link_request, patient) for link_request, patient in rows]

    def list_incoming_requests(self, current_user: User) -> list[dict]:
        now = datetime.now(timezone.utc)
        rows = (
            self.db.query(PatientLinkRequest, ProfessionalProfile, User)
            .join(ProfessionalProfile, ProfessionalProfile.id == PatientLinkRequest.professional_profile_id)
            .join(User, User.id == ProfessionalProfile.user_id)
            .filter(
                PatientLinkRequest.patient_user_id == current_user.id,
                PatientLinkRequest.status == PatientLinkRequestStatusEnum.PENDING.value,
                PatientLinkRequest.expires_at > now,
            )
            .order_by(PatientLinkRequest.created_at.desc())
            .all()
        )
        return [self._to_incoming_dict(link_request, professional_profile, professional_user) for link_request, professional_profile, professional_user in rows]

    def respond(self, current_user: User, request_id: int, accept: bool) -> dict:
        link_request = (
            self.db.query(PatientLinkRequest)
            .filter(PatientLinkRequest.id == request_id, PatientLinkRequest.patient_user_id == current_user.id)
            .first()
        )
        if not link_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link request not found")
        if link_request.status != PatientLinkRequestStatusEnum.PENDING.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Link request already resolved")

        now = datetime.now(timezone.utc)
        expires_at = link_request.expires_at.replace(tzinfo=timezone.utc) if link_request.expires_at.tzinfo is None else link_request.expires_at
        if expires_at <= now:
            set_database_service_context(self.db, "patient_link_response")
            link_request.status = PatientLinkRequestStatusEnum.EXPIRED.value
            self.db.commit()
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link request has expired")

        set_database_service_context(self.db, "patient_link_response")

        if not accept:
            link_request.status = PatientLinkRequestStatusEnum.REJECTED.value
            link_request.responded_at = now
            self.db.commit()
            self.db.refresh(link_request)
            return self._to_read_dict(link_request)

        if self._has_active_professional_link(self.db, current_user.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already linked to a professional")

        # Deactivate any existing self-service plan — the professional-owned
        # plan created below takes over.
        self.db.query(MonitoringPlan).filter(
            MonitoringPlan.patient_id == current_user.id,
            MonitoringPlan.origin == MonitoringPlanOriginEnum.SELF_SERVICE.value,
            MonitoringPlan.active.is_(True),
        ).update({"active": False})

        # The patient's self-service subscription (if any) is left alone —
        # they keep whatever they're paying for. As a thank-you for bringing
        # a paying subscription, the professional instead gets a bonus AI
        # report generation for this patient (see BONUS_REPORT_CREDITS_ON_LINK).
        subscription = self.db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
        patient_has_paid_subscription = bool(
            subscription
            and subscription.status
            in {SubscriptionStatusEnum.TRIALING.value, SubscriptionStatusEnum.ACTIVE.value, SubscriptionStatusEnum.PAST_DUE.value}
        )

        plan = MonitoringPlan(
            patient_id=current_user.id,
            title="Acompanhamento profissional",
            active=True,
            start_date=now.date(),
            origin=MonitoringPlanOriginEnum.PROFESSIONAL.value,
        )
        self.db.add(plan)
        self.db.flush()
        self.db.add(
            MonitoringProfessional(
                monitoring_plan_id=plan.id,
                professional_profile_id=link_request.professional_profile_id,
                role="responsável",
                active=True,
                bonus_report_credits=BONUS_REPORT_CREDITS_ON_LINK if patient_has_paid_subscription else 0,
            )
        )

        link_request.status = PatientLinkRequestStatusEnum.ACCEPTED.value
        link_request.responded_at = now
        self.db.commit()
        self.db.refresh(link_request)
        return self._to_read_dict(link_request)

    @staticmethod
    def _to_read_dict(link_request: PatientLinkRequest) -> dict:
        return {
            "id": link_request.id,
            "status": link_request.status,
            "created_at": link_request.created_at,
            "expires_at": link_request.expires_at,
            "responded_at": link_request.responded_at,
        }

    @classmethod
    def _to_sent_dict(cls, link_request: PatientLinkRequest, patient: User) -> dict:
        return {**cls._to_read_dict(link_request), "patient_name": patient.name, "patient_email": patient.email}

    @classmethod
    def _to_incoming_dict(cls, link_request: PatientLinkRequest, professional_profile: ProfessionalProfile, professional_user: User) -> dict:
        return {
            **cls._to_read_dict(link_request),
            "professional_name": professional_user.name,
            "professional_specialty": professional_profile.specialty,
        }
