from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.models.models import AiReportCache
from app.services.clinical_data_service import ClinicalDataService


class AiReportClinicalService:
    @staticmethod
    def write_summary(report: AiReportCache, value: str | None) -> None:
        if AiReportClinicalService._disabled():
            report.clinical_summary = value
            report.clinical_summary_encryption_envelope = None
            return
        AiReportClinicalService._service().write_text(report, "clinical_summary", value)

    @staticmethod
    def write_response(report: AiReportCache, value) -> None:
        if AiReportClinicalService._disabled():
            report.ai_response = value
            report.ai_response_encryption_envelope = None
            return
        AiReportClinicalService._service().write_json(report, "ai_response", value)

    @staticmethod
    def hydrate(report: AiReportCache) -> AiReportCache:
        if not (report.clinical_summary_encryption_envelope or report.ai_response_encryption_envelope):
            return report
        service = AiReportClinicalService._service()
        if report.clinical_summary_encryption_envelope:
            set_committed_value(report, "clinical_summary", service.read_text(report, "clinical_summary"))
        if report.ai_response_encryption_envelope:
            set_committed_value(report, "ai_response", service.read_json(report, "ai_response"))
        return report

    @staticmethod
    def _service() -> ClinicalDataService:
        return ClinicalDataService()

    @staticmethod
    def _disabled() -> bool:
        return settings.CLINICAL_ENCRYPTION_PROVIDER == "disabled" and settings.ENV != "production"
