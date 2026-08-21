from http.cookies import SimpleCookie

from fastapi import Response

from app.core.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    LEGACY_REFRESH_COOKIE_PATH,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    clear_auth_cookies,
    set_auth_cookies,
)


def _set_cookie_headers(response: Response) -> list[str]:
    return response.headers.getlist("set-cookie")


def _cookie_by_name(response: Response, name: str) -> SimpleCookie:
    for header in _set_cookie_headers(response):
        cookie = SimpleCookie()
        cookie.load(header)
        if name in cookie:
            return cookie
    raise AssertionError(f"Cookie {name!r} was not set")


def test_auth_cookies_use_host_prefix_compatible_paths():
    response = Response()

    set_auth_cookies(
        response,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
    )

    assert _cookie_by_name(response, ACCESS_COOKIE)[ACCESS_COOKIE]["path"] == "/"
    assert _cookie_by_name(response, REFRESH_COOKIE)[REFRESH_COOKIE]["path"] == REFRESH_COOKIE_PATH
    assert _cookie_by_name(response, CSRF_COOKIE)[CSRF_COOKIE]["path"] == "/"


def test_refresh_and_csrf_cookies_outlive_the_access_cookie():
    response = Response()

    set_auth_cookies(
        response,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
    )

    access = _cookie_by_name(response, ACCESS_COOKIE)[ACCESS_COOKIE]
    refresh = _cookie_by_name(response, REFRESH_COOKIE)[REFRESH_COOKIE]
    csrf = _cookie_by_name(response, CSRF_COOKIE)[CSRF_COOKIE]

    assert access["max-age"] == "3600"
    assert refresh["max-age"] == str(60 * 60 * 24 * 30)
    assert csrf["max-age"] == str(60 * 60 * 24 * 30)
    assert refresh["secure"] is True
    assert refresh["httponly"] is True
    assert refresh["samesite"] == "strict"


def test_clear_auth_cookies_expires_current_and_legacy_refresh_paths():
    response = Response()

    clear_auth_cookies(response)

    refresh_paths = []
    for header in _set_cookie_headers(response):
        cookie = SimpleCookie()
        cookie.load(header)
        if REFRESH_COOKIE in cookie:
            refresh_paths.append(cookie[REFRESH_COOKIE]["path"])

    assert refresh_paths == [REFRESH_COOKIE_PATH, LEGACY_REFRESH_COOKIE_PATH]
