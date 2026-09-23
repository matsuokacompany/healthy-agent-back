import pytest

from app.services.insight_service import InsightService, _bucketize, _SCALE_BAIXA_ALTA, _SCALE_BAIXO_ALTO

_CATEGORIA_KEYS = ("cardiorrespiratorio", "febre")


def build_service(modo: str) -> InsightService:
    return InsightService(api_key="test-key", modo=modo)


def test_rejects_unknown_mode():
    with pytest.raises(ValueError):
        InsightService(api_key="test-key", modo="modo_invalido")


def test_requires_api_key():
    with pytest.raises(ValueError):
        InsightService(api_key="", modo="preventivo")


def test_deteccao_sinais_alerta_requires_categoria_keys():
    with pytest.raises(ValueError):
        InsightService(api_key="test-key", modo="deteccao_sinais_alerta")


def test_deteccao_sinais_alerta_builds_with_categoria_keys():
    service = InsightService(
        api_key="test-key", modo="deteccao_sinais_alerta", categoria_keys=_CATEGORIA_KEYS
    )
    assert service.modo == "deteccao_sinais_alerta"


def test_normalizacao_sintomas_prompt_steers_away_from_bare_generic_term():
    # A ranking card showing just "Dor" repeated gives the professional
    # nothing to act on -- the classifier should prefer a term that
    # carries the location/type the patient's description gives it (e.g.
    # "Dor abdominal") and fall back to the bare term only when the
    # description truly gives no such detail.
    service = build_service("normalizacao_sintomas")

    system_prompt = service.prompt.messages[0].prompt.template

    assert "específic" in system_prompt.lower()
    assert '"Dor"' in system_prompt
    assert "Dor abdominal" in system_prompt


def test_deteccao_schema_accepts_a_known_category_and_none():
    schema = InsightService._build_deteccao_schema(_CATEGORIA_KEYS)
    assert schema(categoria="febre").categoria == "febre"
    assert schema().categoria is None


def test_deteccao_schema_rejects_a_category_outside_the_reviewed_list():
    schema = InsightService._build_deteccao_schema(_CATEGORIA_KEYS)
    with pytest.raises(Exception):
        schema(categoria="categoria_inventada")


def test_bucketize_passes_through_exact_word():
    assert _bucketize("alta", _SCALE_BAIXA_ALTA, "media") == "alta"
    assert _bucketize("moderado", _SCALE_BAIXO_ALTO, "moderado") == "moderado"


def test_bucketize_normalizes_accents_and_case():
    assert _bucketize("Média", _SCALE_BAIXA_ALTA, "media") == "media"
    assert _bucketize(" ALTA ", _SCALE_BAIXA_ALTA, "media") == "alta"


def test_bucketize_classifies_stray_percentage_into_a_bucket():
    assert _bucketize("10%", _SCALE_BAIXA_ALTA, "media") == "baixa"
    assert _bucketize("50%", _SCALE_BAIXA_ALTA, "media") == "media"
    assert _bucketize("90%", _SCALE_BAIXA_ALTA, "media") == "alta"


def test_bucketize_classifies_stray_fraction():
    assert _bucketize("0.2", _SCALE_BAIXA_ALTA, "media") == "baixa"
    assert _bucketize("0.8", _SCALE_BAIXA_ALTA, "media") == "alta"


def test_bucketize_falls_back_to_default_for_unparseable_value():
    assert _bucketize("não sei dizer", _SCALE_BAIXA_ALTA, "media") == "media"
    assert _bucketize(None, _SCALE_BAIXA_ALTA, "media") == "media"


def test_normalize_qualitative_fields_fixes_preventivo_riscos():
    service = build_service("preventivo")
    resultado = {
        "riscos_longo_prazo": [
            {"condicao": "Diabetes tipo 2", "nivel_de_atencao": "20%"},
            {"condicao": "Alzheimer", "nivel_de_atencao": "Moderado"},
        ]
    }
    service._normalize_qualitative_fields(resultado)
    assert resultado["riscos_longo_prazo"][0]["nivel_de_atencao"] == "baixo"
    assert resultado["riscos_longo_prazo"][1]["nivel_de_atencao"] == "moderado"


def test_normalize_qualitative_fields_fixes_avaliacao_clinica():
    service = build_service("avaliacao_clinica")
    resultado = {
        "urgencia": "85%",
        "hipoteses": [{"doenca": "Refluxo", "nivel_de_suspeicao": "Moderado"}],
    }
    service._normalize_qualitative_fields(resultado)
    assert resultado["urgencia"] == "alta"
    assert resultado["hipoteses"][0]["nivel_de_suspeicao"] == "moderado"


def test_normalize_qualitative_fields_trims_avaliacao_clinica_to_five_hipoteses():
    service = build_service("avaliacao_clinica")
    resultado = {"hipoteses": [{"doenca": f"Hipótese {i}", "nivel_de_suspeicao": "baixo"} for i in range(7)]}
    service._normalize_qualitative_fields(resultado)
    assert len(resultado["hipoteses"]) == 5


def test_normalize_qualitative_fields_is_noop_for_resumo_paciente_without_urgencia():
    service = build_service("resumo_paciente")
    resultado = {"resumo": "texto", "pontos_positivos": [], "pontos_de_atencao": [], "sugestao": "texto"}
    original = dict(resultado)
    service._normalize_qualitative_fields(resultado)
    assert resultado == original


def test_normalize_qualitative_fields_fixes_resumo_paciente_urgencia():
    service = build_service("resumo_paciente")
    resultado = {"especialidade_sugerida": "Clínico geral", "urgencia_consulta": "90%"}
    service._normalize_qualitative_fields(resultado)
    assert resultado["urgencia_consulta"] == "alta"


def test_normalize_qualitative_fields_defaults_resumo_paciente_urgencia_to_baixa_when_unparseable():
    service = build_service("resumo_paciente")
    resultado = {"urgencia_consulta": "não sei dizer"}
    service._normalize_qualitative_fields(resultado)
    assert resultado["urgencia_consulta"] == "baixa"
