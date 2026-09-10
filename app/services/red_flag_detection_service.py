import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Anamnese, User
from app.services.insight_service import InsightService
from app.services.red_flag_symptoms import (
    ANAMNESE_RISK_FACTOR_LABELS,
    CONTEXTUAL_RISK_RULES,
    RED_FLAG_ALL_CATEGORIES,
    RED_FLAG_CATEGORY_BY_KEY,
    RedFlagCategory,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedFlagMatch:
    category: RedFlagCategory
    # Set only for a CONTEXTUAL match -- which risk factor on the patient's
    # anamnese is why this otherwise-routine symptom got escalated. None
    # for an ABSOLUTE match, which doesn't depend on patient history.
    risk_factor_label: str | None = None


class RedFlagDetectionService:
    """Classifies a check-in's free-text symptom_description against the
    short, human-reviewed categories in red_flag_symptoms.py -- both the
    ABSOLUTE tier (always a red flag) and the CONTEXTUAL tier (a red flag
    only given a matching risk factor on the patient's anamnese).

    Best-effort and conservative by design, same posture as
    SymptomNormalizationService: any failure here (missing API key,
    provider error, unparseable response) is logged and swallowed, and an
    unrecognized category key from the model is treated as no match --
    this never invents or guesses a category outside the reviewed list,
    and never blocks a check-in from completing.
    """

    MAX_TOKENS = 60

    @classmethod
    def detect_for_patient(cls, db: Session, user: User, symptom_description: str | None) -> RedFlagMatch | None:
        """The entry point DailyReportService should use: classifies the
        description, then -- for a CONTEXTUAL-tier result only -- cross-
        references the patient's anamnese risk factors (CONTEXTUAL_RISK_RULES)
        and returns None unless one of them actually applies. An ABSOLUTE
        match is returned as-is, since it doesn't depend on history."""
        category = cls.detect(symptom_description)
        if not category:
            return None
        if category.tier == "absoluto":
            return RedFlagMatch(category=category)

        anamnese = db.query(Anamnese).filter(Anamnese.user_id == user.id).first()
        if not anamnese:
            return None
        for field, triggered_categories in CONTEXTUAL_RISK_RULES.items():
            if category.key in triggered_categories and getattr(anamnese, field, False):
                return RedFlagMatch(category=category, risk_factor_label=ANAMNESE_RISK_FACTOR_LABELS[field])
        return None

    @classmethod
    def detect(cls, symptom_description: str | None) -> RedFlagCategory | None:
        if not symptom_description or not settings.OPENAI_API_KEY:
            return None
        try:
            return cls._detect(symptom_description)
        except Exception:
            logger.exception("Red flag detection failed for description=%r", symptom_description)
            return None

    @classmethod
    def _detect(cls, symptom_description: str) -> RedFlagCategory | None:
        categories_text = "\n".join(
            f'- {category.key}: {category.label} (ex.: {"; ".join(category.example_phrases[:4])})'
            for category in RED_FLAG_ALL_CATEGORIES
        )
        prompt_input = (
            f"CATEGORIAS DISPONÍVEIS (responda só com a chave, nunca o rótulo):\n{categories_text}\n\n"
            f"DESCRIÇÃO DO PACIENTE: {symptom_description}"
        )

        service = InsightService(
            api_key=settings.OPENAI_API_KEY,
            modo="deteccao_sinais_alerta",
            model=settings.AI_REPORT_MODEL,
            max_tokens=cls.MAX_TOKENS,
        )
        result = service.gerar_interpretacao(prompt_input)
        category_key = result.get("categoria")
        if not isinstance(category_key, str):
            return None
        return RED_FLAG_CATEGORY_BY_KEY.get(category_key.strip())
