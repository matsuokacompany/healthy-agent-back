from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.models.models import Anamnese
from app.services.clinical_data_service import ClinicalDataService
from app.services.red_flag_symptoms import ANAMNESE_RISK_FACTOR_FIELDS


class AnamneseClinicalService:
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
        if settings.CLINICAL_ENCRYPTION_PROVIDER == "disabled" and settings.ENV != "production":
            anamnese.info = info
            anamnese.info_encryption_envelope = None
            return
        ClinicalDataService().write_text(anamnese, "info", info)

    @staticmethod
    def hydrate(anamnese: Anamnese) -> Anamnese:
        if not anamnese.info_encryption_envelope:
            return anamnese
        value = ClinicalDataService().read_text(anamnese, "info")
        set_committed_value(anamnese, "info", value)
        return anamnese
