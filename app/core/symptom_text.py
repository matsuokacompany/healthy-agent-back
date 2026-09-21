import re
import unicodedata

# Zero-width/format Unicode characters (joiners, marks, BOM, bidi controls)
# that an LLM can emit inside an otherwise-plain word without changing how
# it renders -- str.strip() does not remove these (they aren't
# str.isspace()), so a label carrying one silently compares unequal to the
# visually identical label without it.
_INVISIBLE_RE = re.compile("[​-‏‪-‮⁠-⁤﻿]")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_symptom_label(label: str) -> str:
    """Canonical form to *store* a SymptomTerm.label as: Unicode-normalized
    (NFKC), invisible/format characters removed, internal whitespace
    collapsed to a single space, and outer whitespace trimmed. Preserves
    case and accents -- this is what a human should see, just with the
    characters that don't render stripped out so two AI-classified labels
    that look the same are also byte-identical.
    """
    text = unicodedata.normalize("NFKC", label)
    text = _INVISIBLE_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_symptom_label(label: str) -> str:
    """Comparison/merge key for a SymptomTerm label: clean_symptom_label()
    plus casefold. Two labels sharing this key are the same symptom even
    if they're stored as distinct rows (e.g. pre-existing dirty data from
    before clean_symptom_label() was applied at write time) -- callers
    that display counts (PatientDashboardService._get_top_symptom_terms)
    merge on this key rather than trusting the raw label to be unique.
    """
    return clean_symptom_label(label).casefold()
