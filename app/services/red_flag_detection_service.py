import logging

from app.core.config import settings
from app.services.insight_service import InsightService
from app.services.red_flag_symptoms import RED_FLAG_ABSOLUTE_CATEGORIES, RED_FLAG_CATEGORY_BY_KEY, RedFlagCategory

logger = logging.getLogger(__name__)


class RedFlagDetectionService:
    """Classifies a check-in's free-text symptom_description against the
    short, human-reviewed RED_FLAG_ABSOLUTE categories in
    red_flag_symptoms.py.

    Best-effort and conservative by design, same posture as
    SymptomNormalizationService: any failure here (missing API key,
    provider error, unparseable response) is logged and swallowed, and an
    unrecognized category key from the model is treated as no match --
    this never invents or guesses a category outside the reviewed list,
    and never blocks a check-in from completing.
    """

    MAX_TOKENS = 60

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
            for category in RED_FLAG_ABSOLUTE_CATEGORIES
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
