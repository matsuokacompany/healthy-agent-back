from app.core.config import settings
from app.services.red_flag_detection_service import RedFlagDetectionService


class FakeInsightService:
    next_result: dict = {}
    last_prompt_input: str | None = None

    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        FakeInsightService.last_prompt_input = relatorio_texto
        return FakeInsightService.next_result


class RaisingInsightService:
    def __init__(self, **kwargs):
        pass

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        raise RuntimeError("provider unavailable")


def test_detect_returns_none_without_an_api_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )

    assert RedFlagDetectionService.detect("dor no peito muito forte") is None


def test_detect_returns_none_for_an_empty_description(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )

    assert RedFlagDetectionService.detect("") is None
    assert RedFlagDetectionService.detect(None) is None


def test_detect_returns_the_matching_category(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": "cardiorrespiratorio"}

    result = RedFlagDetectionService.detect("aperto forte no peito e falta de ar")

    assert result is not None
    assert result.key == "cardiorrespiratorio"
    assert "peito" in FakeInsightService.last_prompt_input or "respira" in FakeInsightService.last_prompt_input.lower()


def test_detect_returns_none_when_the_model_reports_no_match(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": None}

    assert RedFlagDetectionService.detect("coceira leve no braço") is None


def test_detect_never_invents_a_category_outside_the_reviewed_list(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": "categoria_que_nao_existe"}

    assert RedFlagDetectionService.detect("qualquer coisa") is None


def test_detect_swallows_a_provider_failure(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        RaisingInsightService,
    )

    assert RedFlagDetectionService.detect("dor no peito") is None
