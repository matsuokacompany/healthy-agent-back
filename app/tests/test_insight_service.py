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


def test_normalize_qualitative_fields_fixes_preventivo_scenarios():
    service = build_service("preventivo")
    resultado = {
        "cenarios": {
            "otimista": {"probabilidade": "20%"},
            "intermediario": {"probabilidade": "media"},
            "grave": {"probabilidade": "muito alta, quase certeza"},
        }
    }
    service._normalize_qualitative_fields(resultado)
    assert resultado["cenarios"]["otimista"]["probabilidade"] == "baixa"
    assert resultado["cenarios"]["intermediario"]["probabilidade"] == "media"
    assert resultado["cenarios"]["grave"]["probabilidade"] == "alta"


def test_normalize_qualitative_fields_fixes_avaliacao_clinica():
    service = build_service("avaliacao_clinica")
    resultado = {
        "urgencia": "85%",
        "avaliacao_clinica": {"nivel_de_suspeicao": "Moderado"},
    }
    service._normalize_qualitative_fields(resultado)
    assert resultado["urgencia"] == "alta"
    assert resultado["avaliacao_clinica"]["nivel_de_suspeicao"] == "moderado"


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
