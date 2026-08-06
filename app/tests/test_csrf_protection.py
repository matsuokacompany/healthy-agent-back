from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


client = TestClient(app)


def test_cookie_authenticated_mutation_requires_matching_csrf_token():
    response = client.post(
        "/api/auth/logout",
        cookies={
            settings.AUTH_ACCESS_COOKIE_NAME: "access-token",
            settings.AUTH_CSRF_COOKIE_NAME: "csrf-token",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid CSRF token"


def test_cookie_authenticated_mutation_accepts_matching_csrf_token():
    response = client.post(
        "/api/auth/logout",
        cookies={
            settings.AUTH_ACCESS_COOKIE_NAME: "access-token",
            settings.AUTH_CSRF_COOKIE_NAME: "csrf-token",
        },
        headers={settings.AUTH_CSRF_HEADER_NAME: "csrf-token"},
    )

    assert response.status_code == 204


def test_bearer_authenticated_mutation_does_not_require_csrf_token():
    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": "Bearer api-client-token"},
    )

    assert response.status_code == 204


def test_csrf_endpoint_returns_host_only_cookie_value():
    response = client.get(
        "/api/auth/csrf",
        cookies={settings.AUTH_CSRF_COOKIE_NAME: "csrf-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"csrf_token": "csrf-token"}
    assert response.headers[settings.AUTH_CSRF_HEADER_NAME] == "csrf-token"
    assert response.headers["Cache-Control"] == "no-store"


def test_csrf_endpoint_rejects_request_without_cookie():
    response = client.get("/api/auth/csrf")

    assert response.status_code == 401
