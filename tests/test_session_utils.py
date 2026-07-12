"""Tests unitaires pour session_utils."""
from __future__ import annotations

import time

import jwt
import pytest
from fastapi import Response
from starlette.requests import Request

import config
from session_utils import (
    clear_session_cookie,
    create_session_token,
    decode_session_token,
    get_session_user,
    set_session_cookie,
)


@pytest.fixture
def session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SESSION_SECRET", "unit-test-session-secret-32chars")
    monkeypatch.setattr(config, "SESSION_TTL_HOURS", 1)
    monkeypatch.setattr(config, "SESSION_COOKIE_NAME", "tc_session")
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", False)


def test_create_and_decode_session_token(session_secret: None) -> None:
    token = create_session_token(
        {"id_user": 42, "email": "user@example.com", "auth_provider": "microsoft"}
    )
    claims = decode_session_token(token)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["email"] == "user@example.com"
    assert claims["provider"] == "microsoft"


def test_decode_session_token_rejects_tampered_token(session_secret: None) -> None:
    token = create_session_token({"id_user": 1, "email": "a@b.com"})
    tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
    assert decode_session_token(tampered) is None


def test_get_session_user_from_cookie(session_secret: None) -> None:
    token = create_session_token({"id_user": 7, "email": "x@y.com", "auth_provider": "local"})
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", f"tc_session={token}".encode())],
    }
    request = Request(scope)
    user = get_session_user(request)
    assert user is not None
    assert user["sub"] == "7"


def test_set_and_clear_session_cookie(session_secret: None) -> None:
    response = Response()
    set_session_cookie(response, "jwt-token-value")
    set_cookie = response.headers.get("set-cookie", "")
    assert "tc_session=jwt-token-value" in set_cookie
    assert "httponly" in set_cookie.lower()

    cleared = Response()
    clear_session_cookie(cleared)
    assert "tc_session=" in cleared.headers.get("set-cookie", "")
