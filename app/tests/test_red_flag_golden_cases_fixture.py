"""Schema sanity checks for app/scripts/fixtures/red_flag_golden_cases.json --
no network, no AI call. Guards against the fixture silently rotting (a typo'd
category key, a risk-factor field renamed in red_flag_symptoms.py) rather
than validating the classifier's actual accuracy, which is what
app/scripts/red_flag_eval.py is for."""

import json
from pathlib import Path

from app.services.red_flag_symptoms import ANAMNESE_RISK_FACTOR_FIELDS, RED_FLAG_CATEGORY_BY_KEY

FIXTURE_PATH = Path(__file__).parent.parent / "scripts" / "fixtures" / "red_flag_golden_cases.json"


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


def test_fixture_is_valid_json_with_cases():
    cases = _load_cases()
    assert len(cases) > 0


def test_every_case_has_a_unique_id():
    cases = _load_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_every_expected_category_is_a_real_reviewed_category():
    for case in _load_cases():
        expected = case.get("categoria_esperada")
        if expected is not None:
            assert expected in RED_FLAG_CATEGORY_BY_KEY, f"{case['id']}: {expected!r} is not a known category key"


def test_every_risk_factor_field_is_a_real_anamnese_field():
    for case in _load_cases():
        field = case.get("fator_risco_field")
        if field is not None:
            assert field in ANAMNESE_RISK_FACTOR_FIELDS, f"{case['id']}: {field!r} is not a known anamnese risk factor field"


def test_a_contextual_case_always_states_whether_the_risk_factor_is_present():
    for case in _load_cases():
        if case["tier"] == "contextual":
            assert case.get("fator_risco_field") is not None, f"{case['id']}: contextual case missing fator_risco_field"
            assert isinstance(case.get("fator_risco_presente"), bool), f"{case['id']}: fator_risco_presente must be true/false"


def test_no_case_is_marked_physician_reviewed_yet():
    # Documents current state rather than enforcing a rule: flip this once
    # a physician actually reviews the set, so the fixture's _readme claim
    # ("DRAFT... NOT clinically validated") stays true only until it isn't.
    assert all(case.get("revisado_pelo_medico") is False for case in _load_cases())
