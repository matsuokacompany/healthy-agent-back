import pytest
from pydantic import ValidationError

from app.models.schemas import AnamneseBase, InsightRequest, MonitoringPlanCreate, ProfessionalProfileCreate


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AnamneseBase, {"info": "a" * 20_001}),
        (
            MonitoringPlanCreate,
            {"patient_id": 1, "title": "a" * 256},
        ),
        (
            ProfessionalProfileCreate,
            {"user_id": 1, "bio": "a" * 2_001},
        ),
        (InsightRequest, {"relatorio_texto": "a" * 6_001}),
    ],
)
def test_unbounded_text_inputs_are_rejected(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


def test_control_characters_are_rejected_from_clinical_text():
    with pytest.raises(ValidationError):
        AnamneseBase(info="texto\x00oculto")


def test_plain_text_is_preserved_instead_of_interpreted_as_html():
    value = "<b>relato do paciente</b>"
    assert AnamneseBase(info=value).info == value
