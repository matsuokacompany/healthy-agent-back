from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.models.models import Anamnese
from app.services.clinical_data_service import ClinicalDataService
from app.services.red_flag_symptoms import ANAMNESE_RISK_FACTOR_FIELDS


class AnamneseClinicalService:
    ALLERGY_FIELDS = ("medication_allergies", "food_restrictions")

    @staticmethod
    def write_risk_factors(anamnese: Anamnese, risk_factors: dict) -> None:
        """Applies whichever of the reviewed risk-factor fields (see
        red_flag_symptoms.ANAMNESE_RISK_FACTOR_FIELDS) are present in
        `risk_factors` -- callers pass payload.dict(exclude_unset=True) so a
        partial update never resets fields the caller didn't mention. Keys
        outside the reviewed list are ignored rather than raising, since the
        Pydantic schema already constrains what a client can send here."""
        for field in ANAMNESE_RISK_FACTOR_FIELDS:
            if field in risk_factors:
                setattr(anamnese, field, risk_factors[field])

    @staticmethod
    def initial_plaintext(info: str) -> str | None:
        if settings.CLINICAL_ENCRYPTION_PROVIDER == "disabled" and settings.ENV != "production":
            return info
        return info if settings.CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED else None

    @staticmethod
    def write(anamnese: Anamnese, info: str) -> None:
        AnamneseClinicalService._write_field(anamnese, "info", info)

    @staticmethod
    def write_allergies(anamnese: Anamnese, values: dict) -> None:
        """Same presence-vs-absence contract as `write_risk_factors`: pass
        `payload.dict(exclude_unset=True)` so a partial update only touches
        the keys the caller actually sent -- an explicit `null` clears a
        field (ClinicalDataService.write_text treats None as "clear"), while
        an absent key leaves the stored value untouched."""
        for field in AnamneseClinicalService.ALLERGY_FIELDS:
            if field in values:
                AnamneseClinicalService._write_field(anamnese, field, values[field])

    @staticmethod
    def _write_field(anamnese: Anamnese, field: str, value: str | None) -> None:
        if settings.CLINICAL_ENCRYPTION_PROVIDER == "disabled" and settings.ENV != "production":
            setattr(anamnese, field, value)
            setattr(anamnese, f"{field}_encryption_envelope", None)
            return
        ClinicalDataService().write_text(anamnese, field, value)

    @staticmethod
    def hydrate(anamnese: Anamnese) -> Anamnese:
        fields = [
            field
            for field in ("info", *AnamneseClinicalService.ALLERGY_FIELDS)
            if getattr(anamnese, f"{field}_encryption_envelope")
        ]
        if not fields:
            return anamnese
        service = ClinicalDataService()
        for field in fields:
            set_committed_value(anamnese, field, service.read_text(anamnese, field))
        return anamnese
