from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import legal_routes


def build_client():
    app = FastAPI()
    app.include_router(legal_routes.router, prefix="/legal")
    return TestClient(app)


def test_get_terms_of_use_requires_no_auth_and_returns_markdown():
    client = build_client()

    response = client.get("/legal/termos-de-uso")

    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "Termos de Uso" in response.text


def test_get_privacy_policy():
    client = build_client()

    response = client.get("/legal/politica-de-privacidade")

    assert response.status_code == 200
    assert "Política de Privacidade" in response.text


def test_get_refund_policy():
    client = build_client()

    response = client.get("/legal/politica-de-reembolso")

    assert response.status_code == 200
    assert "Política de Reembolso" in response.text


def test_unknown_slug_returns_404():
    client = build_client()

    response = client.get("/legal/nao-existe")

    assert response.status_code == 404


def test_path_traversal_slug_is_rejected():
    client = build_client()

    response = client.get("/legal/..%2F..%2Fapp%2Fmain")

    assert response.status_code == 404
