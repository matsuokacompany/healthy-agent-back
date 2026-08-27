from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.models.models import SelfMonitoringInsight
from app.services.clinical_data_service import ClinicalDataService


class SelfMonitoringInsightClinicalService:
    @staticmethod
    def write_response(insight: SelfMonitoringInsight, value) -> None:
        if SelfMonitoringInsightClinicalService._disabled():
            insight.insight_response = value
            insight.insight_response_encryption_envelope = None
            return
        SelfMonitoringInsightClinicalService._service().write_json(insight, "insight_response", value)

    @staticmethod
    def hydrate(insight: SelfMonitoringInsight) -> SelfMonitoringInsight:
        if not insight.insight_response_encryption_envelope:
            return insight
        service = SelfMonitoringInsightClinicalService._service()
        set_committed_value(insight, "insight_response", service.read_json(insight, "insight_response"))
        return insight

    @staticmethod
    def _service() -> ClinicalDataService:
        return ClinicalDataService()

    @staticmethod
    def _disabled() -> bool:
        return settings.CLINICAL_ENCRYPTION_PROVIDER == "disabled" and settings.ENV != "production"
