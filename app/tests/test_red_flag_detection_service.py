from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import Anamnese, User
from app.services.red_flag_detection_service import RedFlagDetectionService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def create_user(db, **anamnese_risk_factors):
    user = User(name="Teste", email=f"u-{datetime.now().timestamp()}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    if anamnese_risk_factors:
        anamnese = Anamnese(user_id=user.id, **anamnese_risk_factors)
        db.add(anamnese)
        db.commit()
    return user


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


def test_detect_for_patient_passes_through_an_absolute_match_without_an_anamnese(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": "cardiorrespiratorio"}

    db = build_session()
    user = create_user(db)

    match = RedFlagDetectionService.detect_for_patient(db, user, "aperto forte no peito")

    assert match is not None
    assert match.category.key == "cardiorrespiratorio"
    assert match.risk_factor_label is None


def test_detect_for_patient_escalates_a_contextual_match_with_the_matching_risk_factor(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": "falta_de_ar_leve"}

    db = build_session()
    user = create_user(db, risk_heart_disease=True)

    match = RedFlagDetectionService.detect_for_patient(db, user, "um pouco de falta de ar ao subir escadas")

    assert match is not None
    assert match.category.key == "falta_de_ar_leve"
    assert match.risk_factor_label == "Doença cardíaca"


def test_detect_for_patient_returns_none_for_a_contextual_match_without_the_risk_factor(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": "falta_de_ar_leve"}

    db = build_session()
    user = create_user(db, risk_heart_disease=False, risk_diabetes=True)

    match = RedFlagDetectionService.detect_for_patient(db, user, "um pouco de falta de ar ao subir escadas")

    assert match is None


def test_detect_for_patient_returns_none_for_a_contextual_match_with_no_anamnese(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": "febre"}

    db = build_session()
    user = create_user(db)

    match = RedFlagDetectionService.detect_for_patient(db, user, "febre baixa")

    assert match is None


def test_detect_for_patient_returns_none_when_there_is_no_match_at_all(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.red_flag_detection_service.InsightService",
        FakeInsightService,
    )
    FakeInsightService.next_result = {"categoria": None}

    db = build_session()
    user = create_user(db, risk_heart_disease=True)

    assert RedFlagDetectionService.detect_for_patient(db, user, "coceira leve") is None
