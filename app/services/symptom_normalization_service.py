import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.symptom_text import clean_symptom_label, normalize_symptom_label
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
    def clear(cls, db: Session, report: DailyReport) -> None:
        """Removes any SymptomTerm links left over from a previous answer.

        Called when a patient edits a completed check-in away from "had
        symptoms" (or deletes it outright): the description that produced
        those links no longer applies, so leaving them in
        daily_report_symptom_terms would misattribute terms to a report
        that, per the patient's own correction, never had them.
        """
        report_id = report.id
        try:
            set_database_service_context(db, "symptom_normalization")
            deleted = (
                db.query(DailyReportSymptomTerm)
                .filter(DailyReportSymptomTerm.daily_report_id == report_id)
                .delete()
            )
            db.commit()
            if deleted:
                logger.info("Cleared %d symptom term link(s) for daily_report_id=%s", deleted, report_id)
        except Exception:
            db.rollback()
            logger.exception("Failed to clear symptom terms for daily_report_id=%s", report_id)

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
        # Captured up front: a flush failure below expires every object in
        # the session's identity map (this is SQLAlchemy's normal rollback
        # behavior, not something the except block below controls), so
        # `report.id` could itself need a DB round-trip by the time we get
        # to logging — on a session that, at that exact moment, is still in
        # the broken "pending rollback" state a query would need `db.rollback()`
        # for. Reading it now avoids that.
        report_id = report.id
        try:
            cls._normalize(db, report, symptom_description)
        except Exception:
            # Roll back BEFORE logging (or anything else): a failure
            # partway through _normalize (e.g. a flush-time IntegrityError
            # while creating a new SymptomTerm) leaves the session in
            # SQLAlchemy's "pending rollback" state — every later query on
            # it raises PendingRollbackError until this runs. Callers that
            # reuse the same session across many reports in one batch
            # (SymptomTermsBackfillService) would otherwise have every
            # report AFTER the failing one silently no-op too, since that
            # error is itself just another Exception this same except
            # block swallows.
            db.rollback()
            logger.exception("Symptom normalization failed for daily_report_id=%s", report_id)

    @classmethod
    def _normalize(cls, db: Session, report: DailyReport, symptom_description: str) -> None:
        vocabulary = db.query(SymptomTerm).order_by(SymptomTerm.label.asc()).all()
        vocabulary_text = ", ".join(term.label for term in vocabulary) or "(vocabulário ainda vazio)"

        # Context from the patient's most recent PRIOR symptomatic check-in
        # (if any) — lets the model resolve a deictic answer like "mesma
        # dor, mesmo lugar" onto the same term(s) already recorded instead
        # of inventing a new, unrelated-looking entry. prev_context doubles
        # as the base for this report's own streak_days/origin_report_id
        # below: term_id -> (streak_days, origin_report_id).
        prev_context, previous_terms_text = cls._previous_symptom_context(db, report)
        context_block = ""
        if previous_terms_text:
            context_block = (
                f"SINTOMA(S) DO CHECK-IN ANTERIOR DESTE PACIENTE: {previous_terms_text}\n"
                "Se a descrição do paciente indicar que é o mesmo sintoma do check-in "
                "anterior (ex.: \"mesma dor\", \"igual\", \"mesmo lugar\", \"continua\", "
                "\"segue igual\"), responda com EXATAMENTE o(s) mesmo(s) termo(s) listado(s) "
                "acima, em vez de propor um termo novo.\n\n"
            )
        prompt_input = (
            f"VOCABULÁRIO DISPONÍVEL: {vocabulary_text}\n\n"
            f"{context_block}"
            f"DESCRIÇÃO DO PACIENTE: {symptom_description}"
        )

        service = InsightService(
            api_key=settings.OPENAI_API_KEY,
            modo="normalizacao_sintomas",
            model=settings.AI_REPORT_MODEL,
            max_tokens=cls.MAX_TOKENS,
        )
        result = service.gerar_interpretacao(prompt_input)
        # Diagnostic, but never the clinical free text itself -- app logs
        # don't get the same encryption/retention treatment as the DB
        # column (docs/security.md: "Nunca registre os valores clínicos ou
        # os envelopes"), so logging symptom_description here would quietly
        # defeat clinical field encryption for every check-in. The
        # description's length is still enough to tell an empty/near-empty
        # classifier input apart from a real under-extraction.
        logger.info(
            "Symptom normalization result for daily_report_id=%s: description_len=%d termos=%r",
            report.id, len(symptom_description), result.get("termos"),
        )
        labels = [
            clean_symptom_label(label)[: cls.MAX_TERM_LENGTH]
            for label in (result.get("termos") or [])
            if isinstance(label, str) and label.strip()
        ]
        labels = [label for label in labels if label]
        if not labels:
            return

        # Writes need service context — this session's identity context
        # (patient or bot) has no write grant on either table (see the RLS
        # policies in alembic 0028).
        set_database_service_context(db, "symptom_normalization")

        by_normalized = {normalize_symptom_label(term.label): term.id for term in vocabulary}
        resolved_term_ids: list[int] = []
        for label in labels:
            key = normalize_symptom_label(label)
            term_id = by_normalized.get(key)
            if term_id is None:
                new_term = SymptomTerm(label=label)
                db.add(new_term)
                db.flush()
                by_normalized[key] = new_term.id
                term_id = new_term.id
            resolved_term_ids.append(term_id)

        db.query(DailyReportSymptomTerm).filter(DailyReportSymptomTerm.daily_report_id == report.id).delete()
        for term_id in dict.fromkeys(resolved_term_ids):  # de-dupe, keep first-seen order
            prev = prev_context.get(term_id)
            streak_days = (prev[0] if prev else 0) + 1
            # None here means THIS report is the origin (nothing to chain
            # to) -- prev[1] is already resolved to the true origin by
            # _previous_symptom_context, not just "yesterday", so the
            # detailed description survives any number of "mesma dor" days.
            origin_report_id = prev[1] if prev else None
            db.add(
                DailyReportSymptomTerm(
                    daily_report_id=report.id,
                    symptom_term_id=term_id,
                    patient_id=report.user_id,
                    streak_days=streak_days,
                    origin_report_id=origin_report_id,
                )
            )
        db.commit()

    @staticmethod
    def _previous_symptom_context(db: Session, report: DailyReport) -> tuple[dict[int, tuple[int, int]], str]:
        """Looks up the patient's most recent OTHER symptomatic check-in
        (any status, any distance in time — a missed day in between is fine,
        the reference is still "the last time you told us") and returns its
        term ids -> (streak_days, origin_report_id) (the base this report's
        own streak/origin build on — origin_report_id is resolved to the
        previous report's own id when IT has no origin, i.e. it IS one)
        plus a display string for the prompt's context block."""
        previous_report = (
            db.query(DailyReport)
            .filter(
                DailyReport.user_id == report.user_id,
                DailyReport.id != report.id,
                DailyReport.had_symptoms.is_(True),
            )
            .order_by(DailyReport.report_date.desc(), DailyReport.id.desc())
            .first()
        )
        if previous_report is None:
            return {}, ""

        rows = (
            db.query(
                DailyReportSymptomTerm.symptom_term_id,
                SymptomTerm.label,
                DailyReportSymptomTerm.streak_days,
                DailyReportSymptomTerm.origin_report_id,
            )
            .join(SymptomTerm, SymptomTerm.id == DailyReportSymptomTerm.symptom_term_id)
            .filter(DailyReportSymptomTerm.daily_report_id == previous_report.id)
            .all()
        )
        prev_context = {
            term_id: (streak_days, origin_report_id or previous_report.id)
            for term_id, _label, streak_days, origin_report_id in rows
        }
        previous_terms_text = ", ".join(dict.fromkeys(label for _term_id, label, _streak_days, _origin in rows))
        return prev_context, previous_terms_text
