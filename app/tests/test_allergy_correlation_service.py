from types import SimpleNamespace

from app.services.allergy_correlation_service import AllergyCorrelationService


def anamnese(medication_allergies=None, food_restrictions=None):
    return SimpleNamespace(medication_allergies=medication_allergies, food_restrictions=food_restrictions)


def test_matches_a_food_restriction_mentioned_in_lifestyle_notes():
    # Deliberately literal, not semantic: "leite" (milk) would not match
    # "lactose" even though milk contains lactose -- this only ever echoes
    # back a term the patient themselves typed, never infers relationships
    # between foods and their components.
    matches = AllergyCorrelationService.find_matches(
        anamnese(food_restrictions="amendoim"),
        symptom_description=None,
        lifestyle_notes="Comi um doce com amendoim e depois passei mal.",
    )
    assert matches == ["amendoim"]


def test_matches_a_medication_allergy_mentioned_in_symptom_description():
    matches = AllergyCorrelationService.find_matches(
        anamnese(medication_allergies="Penicilina"),
        symptom_description="Tomei penicilina para a infecção e apareceu uma coceira forte.",
        lifestyle_notes=None,
    )
    assert matches == ["Penicilina"]


def test_matches_multiple_terms_across_both_fields():
    matches = AllergyCorrelationService.find_matches(
        anamnese(medication_allergies="Dipirona", food_restrictions="Camarão"),
        symptom_description="Tomei dipirona pela dor de cabeça.",
        lifestyle_notes="Comi camarão no almoço de hoje.",
    )
    assert set(matches) == {"Dipirona", "Camarão"}


def test_no_match_when_term_does_not_appear_in_either_field():
    matches = AllergyCorrelationService.find_matches(
        anamnese(medication_allergies="Penicilina", food_restrictions="Lactose"),
        symptom_description="Dor de cabeça leve.",
        lifestyle_notes="Comi uma salada.",
    )
    assert matches == []


def test_returns_empty_without_anamnese():
    matches = AllergyCorrelationService.find_matches(
        None, symptom_description="Comi camarão", lifestyle_notes=None
    )
    assert matches == []


def test_returns_empty_when_anamnese_has_no_allergies_registered():
    matches = AllergyCorrelationService.find_matches(
        anamnese(), symptom_description="Comi camarão e passei mal", lifestyle_notes=None
    )
    assert matches == []


def test_uses_word_boundaries_to_avoid_partial_word_false_positives():
    # "Ovo" should not match inside "óvulos" or similar unrelated words.
    matches = AllergyCorrelationService.find_matches(
        anamnese(food_restrictions="Ovo"),
        symptom_description="Fiz um exame de óvulos hoje.",
        lifestyle_notes=None,
    )
    assert matches == []


def test_ignores_short_terms_below_the_minimum_length():
    matches = AllergyCorrelationService.find_matches(
        anamnese(food_restrictions="Sal, Leite"),
        symptom_description="Comi bastante sal no almoço.",
        lifestyle_notes=None,
    )
    assert matches == []


def test_splits_terms_on_common_separators():
    matches = AllergyCorrelationService.find_matches(
        anamnese(food_restrictions="Amendoim; Castanha e Leite ou Soja"),
        symptom_description=None,
        lifestyle_notes="Comi um bolo de castanha no aniversário.",
    )
    assert matches == ["Castanha"]
