from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Supplement, SupplementDosagePeriodEnum, User


class SupplementService:
    """Patient-managed list of supplements/medications — self-owned, unlike
    Anamnese.info which is professional-authored. Read by
    DailyReportService/BotService to name them in the self-service
    WhatsApp medication-adherence question."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_patient(self, patient_id: int) -> list[Supplement]:
        return (
            self.db.query(Supplement)
            .filter(Supplement.patient_id == patient_id)
            .order_by(Supplement.created_at.asc())
            .all()
        )

    @staticmethod
    def list_names(supplements: list[Supplement]) -> list[str]:
        return [supplement.name for supplement in supplements]

    @staticmethod
    def is_active(supplement: Supplement, today: date | None = None) -> bool:
        """Whether this supplement's course is still running -- False once
        `duration_days` days have elapsed since `started_at`. None
        `duration_days` means indeterminate/ongoing, always active."""
        if supplement.duration_days is None:
            return True
        today = today or datetime.now(timezone.utc).date()
        return (today - supplement.started_at).days < supplement.duration_days

    @classmethod
    def list_active_names(cls, supplements: list[Supplement], today: date | None = None) -> list[str]:
        return [supplement.name for supplement in supplements if cls.is_active(supplement, today)]

    def create(
        self,
        patient: User,
        name: str,
        *,
        dosage_times: int = 1,
        dosage_period: SupplementDosagePeriodEnum | str = SupplementDosagePeriodEnum.DAY,
        duration_days: int | None = None,
    ) -> Supplement:
        # Accepts either this module's enum or the (identical-valued) Pydantic
        # schema enum from the request payload -- both are str subclasses, so
        # normalize via .value/str() rather than an isinstance check that
        # would only match one of them.
        dosage_period_value = dosage_period.value if hasattr(dosage_period, "value") else str(dosage_period)
        supplement = Supplement(
            patient_id=patient.id,
            name=name,
            dosage_times=dosage_times,
            dosage_period=dosage_period_value,
            duration_days=duration_days,
        )
        self.db.add(supplement)
        self.db.commit()
        self.db.refresh(supplement)
        return supplement

    def delete(self, patient: User, supplement_id: int) -> bool:
        supplement = (
            self.db.query(Supplement)
            .filter(Supplement.id == supplement_id)
            .filter(Supplement.patient_id == patient.id)
            .first()
        )
        if not supplement:
            return False
        self.db.delete(supplement)
        self.db.commit()
        return True
