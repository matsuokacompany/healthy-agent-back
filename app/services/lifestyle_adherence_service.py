import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import DailyReport
from app.services.insight_service import InsightService

logger = logging.getLogger(__name__)


class LifestyleAdherenceService:
    """Extracts diet_adherence and medication_adherence from the single
    free-text reply to the combined self-service follow-up question (see
    DailyReportService._finish_symptom_flow) — asking one message with two
    clearly numbered questions instead of two separate messages, so the
    WhatsApp conversation doesn't grow past what a self-service check-in
    can afford (see README "Otimização de custo do WhatsApp").

    Best-effort by design, same contract as SymptomNormalizationService:
    the raw reply is already persisted as lifestyle_notes by the caller
    before this runs, so a classification failure here never loses the
    patient's answer, only the two structured booleans derived from it.
    """

    MAX_TOKENS = 100

    @classmethod
    def classify(cls, db: Session, report: DailyReport, text: str | None) -> None:
        if not text:
            return
        if not settings.OPENAI_API_KEY:
            return
        # Captured up front for the same reason as SymptomNormalizationService:
        # a failure below can leave the session needing db.rollback() before
        # report.id is safe to read again for logging.
        report_id = report.id
        try:
            cls._classify(db, report, text)
        except Exception:
            db.rollback()
            logger.exception("Lifestyle adherence classification failed for daily_report_id=%s", report_id)

    @classmethod
    def _classify(cls, db: Session, report: DailyReport, text: str) -> None:
        service = InsightService(
            api_key=settings.OPENAI_API_KEY,
            modo="extracao_estilo_vida",
            model=settings.AI_REPORT_MODEL,
            max_tokens=cls.MAX_TOKENS,
        )
        result = service.gerar_interpretacao(text)
        diet_adherence = result.get("seguiu_dieta")
        medication_adherence = result.get("tomou_remedios")
        if isinstance(diet_adherence, bool):
            report.diet_adherence = diet_adherence
        if isinstance(medication_adherence, bool):
            report.medication_adherence = medication_adherence
        db.commit()
