from sqlalchemy.orm import Session

from app.models.models import Supplement, User


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

    def create(self, patient: User, name: str) -> Supplement:
        supplement = Supplement(patient_id=patient.id, name=name)
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
