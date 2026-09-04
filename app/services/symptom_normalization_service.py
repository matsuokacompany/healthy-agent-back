import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.security_context import set_database_service_context
from app.models.models import DailyReport, DailyReportSymptomTerm, SymptomTerm
from app.services.insight_service import InsightService

logger = logging.getLogger(__name__)


class SymptomNormalizationService:
    """Maps a check-in's free-text symptom_description onto the shared,
    controlled SymptomTerm vocabulary (alembic 0028) — this is what lets
    "diarréia" and "Um pouco de diarréia" count as the same symptom in
    CustomReportService's occurrence counts, instead of two unrelated
    one-off entries.

    Best-effort by design: called right after a check-in with symptoms is
    completed (bot flow or manual edit), but any failure here — missing
    API key, provider error, an unparseable response — is logged and
    swallowed. This is enrichment, never the critical path for a patient's
    check-in actually completing.
    """

    MAX_TOKENS = 150
    MAX_TERM_LENGTH = 80

    @classmethod
    def normalize(cls, db: Session, report: DailyReport, symptom_description: str | None) -> None:
        # Takes the plaintext explicitly rather than reading
        # report.symptom_description: when clinical field encryption is on
        # and CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED is off,
        # ClinicalDataService.write_text nulls that attribute out right
        # after writing the envelope — the caller (which just wrote it)
        # still has the real value in hand, so take it as a parameter
        # instead of re-reading a field that may already be gone.
        if report.had_symptoms is not True or not symptom_description:
            return
        if not settings.OPENAI_API_KEY:
            return
        try:
            cls._normalize(db, report, symptom_description)
        except Exception:
            logger.exception("Symptom normalization failed for daily_report_id=%s", report.id)

    @classmethod
    def _normalize(cls, db: Session, report: DailyReport, symptom_description: str) -> None:
        vocabulary = db.query(SymptomTerm).order_by(SymptomTerm.label.asc()).all()
        vocabulary_text = ", ".join(term.label for term in vocabulary) or "(vocabulário ainda vazio)"
        prompt_input = (
            f"VOCABULÁRIO DISPONÍVEL: {vocabulary_text}\n\n"
            f"DESCRIÇÃO DO PACIENTE: {symptom_description}"
        )

        service = InsightService(
            api_key=settings.OPENAI_API_KEY,
            modo="normalizacao_sintomas",
            model=settings.AI_REPORT_MODEL,
            max_tokens=cls.MAX_TOKENS,
        )
        result = service.gerar_interpretacao(prompt_input)
        labels = [
            label.strip()[: cls.MAX_TERM_LENGTH]
            for label in (result.get("termos") or [])
            if isinstance(label, str) and label.strip()
        ]
        if not labels:
            return

        # Writes need service context — this session's identity context
        # (patient or bot) has no write grant on either table (see the RLS
        # policies in alembic 0028).
        set_database_service_context(db, "symptom_normalization")

        by_lower = {term.label.casefold(): term.id for term in vocabulary}
        resolved_term_ids: list[int] = []
        for label in labels:
            term_id = by_lower.get(label.casefold())
            if term_id is None:
                new_term = SymptomTerm(label=label)
                db.add(new_term)
                db.flush()
                by_lower[label.casefold()] = new_term.id
                term_id = new_term.id
            resolved_term_ids.append(term_id)

        db.query(DailyReportSymptomTerm).filter(DailyReportSymptomTerm.daily_report_id == report.id).delete()
        for term_id in dict.fromkeys(resolved_term_ids):  # de-dupe, keep first-seen order
            db.add(DailyReportSymptomTerm(daily_report_id=report.id, symptom_term_id=term_id, patient_id=report.user_id))
        db.commit()
