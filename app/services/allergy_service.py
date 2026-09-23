from sqlalchemy.orm import Session

from app.models.models import Allergy, AllergySeverityEnum, User


class AllergyService:
    """List of a patient's allergies, each with its own severity level.
    Writable both by the patient themselves (anamnese page) and by a
    professional actively linked to that patient (patient detail page) --
    same `allergies_write` RLS policy as Supplement's `supplements_write`
    (see migration 0046)."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_patient(self, patient_id: int) -> list[Allergy]:
        return (
            self.db.query(Allergy)
            .filter(Allergy.patient_id == patient_id)
            .order_by(Allergy.created_at.asc())
            .all()
        )

    def create(
        self,
        patient: User,
        allergen: str,
        *,
        severity: AllergySeverityEnum | str = AllergySeverityEnum.MODERADA,
    ) -> Allergy:
        return self.create_for_patient(patient.id, allergen, severity=severity)

    def create_for_patient(
        self,
        patient_id: int,
        allergen: str,
        *,
        severity: AllergySeverityEnum | str = AllergySeverityEnum.MODERADA,
    ) -> Allergy:
        # Accepts either this module's enum or the (identical-valued) Pydantic
        # schema enum from the request payload -- both are str subclasses, so
        # normalize via .value/str() rather than an isinstance check that
        # would only match one of them.
        severity_value = severity.value if hasattr(severity, "value") else str(severity)
        allergy = Allergy(patient_id=patient_id, allergen=allergen, severity=severity_value)
        self.db.add(allergy)
        self.db.commit()
        self.db.refresh(allergy)
        return allergy

    def update(self, patient: User, allergy_id: int, **fields) -> Allergy | None:
        return self.update_for_patient(patient.id, allergy_id, **fields)

    def update_for_patient(self, patient_id: int, allergy_id: int, **fields) -> Allergy | None:
        allergy = (
            self.db.query(Allergy)
            .filter(Allergy.id == allergy_id)
            .filter(Allergy.patient_id == patient_id)
            .first()
        )
        if not allergy:
            return None
        severity = fields.get("severity")
        if severity is not None:
            fields["severity"] = severity.value if hasattr(severity, "value") else str(severity)
        for field, value in fields.items():
            setattr(allergy, field, value)
        self.db.commit()
        self.db.refresh(allergy)
        return allergy

    def delete(self, patient: User, allergy_id: int) -> bool:
        return self.delete_for_patient(patient.id, allergy_id)

    def delete_for_patient(self, patient_id: int, allergy_id: int) -> bool:
        allergy = (
            self.db.query(Allergy)
            .filter(Allergy.id == allergy_id)
            .filter(Allergy.patient_id == patient_id)
            .first()
        )
        if not allergy:
            return False
        self.db.delete(allergy)
        self.db.commit()
        return True
