import re

from app.models.models import Anamnese

_SPLIT_PATTERN = re.compile(r",|;|\n|\r| e | ou ", re.IGNORECASE)
MIN_TERM_LENGTH = 4


class AllergyCorrelationService:
    """A literal, factual text match between what the patient registered as
    a medication allergy or food restriction and what they themselves wrote
    in a check-in (the symptom description, or what they ate outside the
    diet) -- never a clinical judgment about whether a reaction actually
    happened. Deliberately separate from red_flag_symptoms.py's curated
    categories: those encode physician-reviewed clinical content and need
    the same review to extend, whereas this only ever echoes back terms the
    patient already typed into their own anamnese, so there's no new
    clinical content being introduced."""

    @classmethod
    def find_matches(
        cls,
        anamnese: Anamnese | None,
        *,
        symptom_description: str | None,
        lifestyle_notes: str | None,
    ) -> list[str]:
        if not anamnese:
            return []
        terms = cls._extract_terms(anamnese.medication_allergies) + cls._extract_terms(anamnese.food_restrictions)
        if not terms:
            return []
        haystacks = [text for text in (symptom_description, lifestyle_notes) if text]
        if not haystacks:
            return []
        matches: list[str] = []
        for term in terms:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE | re.UNICODE)
            if any(pattern.search(haystack) for haystack in haystacks):
                matches.append(term)
        return matches

    @staticmethod
    def _extract_terms(value: str | None) -> list[str]:
        if not value:
            return []
        return [term.strip() for term in _SPLIT_PATTERN.split(value) if len(term.strip()) >= MIN_TERM_LENGTH]
