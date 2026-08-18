from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.models.models import Anamnese
from app.services.clinical_data_service import ClinicalDataService


class AnamneseClinicalService:
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
