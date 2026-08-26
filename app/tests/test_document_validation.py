import httpx
import pytest

from app.core.document_validation import (
    CnpjLookupError,
    cnpj_exists,
    is_valid_cnpj,
    is_valid_cpf,
    only_digits,
)


def test_only_digits_strips_formatting():
    assert only_digits("111.444.777-35") == "11144477735"
    assert only_digits("11.222.333/0001-81") == "11222333000181"


def test_is_valid_cpf_accepts_known_valid_cpf():
    assert is_valid_cpf("11144477735") is True


def test_is_valid_cpf_rejects_wrong_check_digits():
    assert is_valid_cpf("12345678900") is False


def test_is_valid_cpf_rejects_all_same_digit():
    assert is_valid_cpf("11111111111") is False


def test_is_valid_cpf_rejects_wrong_length():
    assert is_valid_cpf("123") is False


def test_is_valid_cnpj_accepts_known_valid_cnpj():
    assert is_valid_cnpj("11222333000181") is True


def test_is_valid_cnpj_rejects_wrong_check_digits():
    assert is_valid_cnpj("11222333000199") is False


def test_is_valid_cnpj_rejects_wrong_length():
    assert is_valid_cnpj("123") is False


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeClient:
    def __init__(self, response=None, raise_error=None):
        self._response = response
        self._raise_error = raise_error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        if self._raise_error:
            raise self._raise_error
        return self._response


def test_cnpj_exists_true_on_200(monkeypatch):
    monkeypatch.setattr(
        "app.core.document_validation.httpx.Client",
        lambda timeout=10.0: _FakeClient(response=_FakeResponse(200)),
    )
    assert cnpj_exists("11222333000181") is True


def test_cnpj_exists_false_on_404(monkeypatch):
    monkeypatch.setattr(
        "app.core.document_validation.httpx.Client",
        lambda timeout=10.0: _FakeClient(response=_FakeResponse(404)),
    )
    assert cnpj_exists("11222333000181") is False


def test_cnpj_exists_raises_lookup_error_on_upstream_failure(monkeypatch):
    monkeypatch.setattr(
        "app.core.document_validation.httpx.Client",
        lambda timeout=10.0: _FakeClient(response=_FakeResponse(500)),
    )
    with pytest.raises(CnpjLookupError):
        cnpj_exists("11222333000181")


def test_cnpj_exists_raises_lookup_error_on_network_failure(monkeypatch):
    monkeypatch.setattr(
        "app.core.document_validation.httpx.Client",
        lambda timeout=10.0: _FakeClient(raise_error=httpx.ConnectError("boom")),
    )
    with pytest.raises(CnpjLookupError):
        cnpj_exists("11222333000181")
