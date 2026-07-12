"""Tests du flux OAuth Microsoft (mock des appels externes et de la base)."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import config
import routers.microsoft_oauth as oauth_module
from session_utils import create_session_token


_FAKE_DISCO = {
    "authorization_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
}


def _state_cookie(state: str, nonce: str = "test-nonce", verifier: str = "test-verifier") -> str:
    payload = {
        "state": state,
        "nonce": nonce,
        "cv": verifier,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    return jwt.encode(payload, config.SESSION_SECRET, algorithm="HS256")


def _mock_token_client(id_token: str = "fake-id-token") -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id_token": id_token}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@patch.object(oauth_module, "_discovery", new_callable=AsyncMock)
def test_microsoft_login_redirects_with_state_cookie(
    mock_discovery: AsyncMock, oauth_client: TestClient
) -> None:
    mock_discovery.return_value = _FAKE_DISCO

    response = oauth_client.get("/auth/microsoft/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith(_FAKE_DISCO["authorization_endpoint"])
    assert "client_id=test-client-id" in response.headers["location"]
    assert oauth_module._OAUTH_STATE_COOKIE in response.cookies


def test_microsoft_callback_invalid_state(oauth_client: TestClient) -> None:
    cookie = _state_cookie("expected-state")
    response = oauth_client.get(
        "/auth/microsoft/callback",
        params={"code": "auth-code", "state": "wrong-state"},
        cookies={oauth_module._OAUTH_STATE_COOKIE: cookie},
    )
    assert response.status_code == 400
    assert "État OAuth invalide" in response.json()["detail"]


@patch.object(oauth_module, "_discovery", new_callable=AsyncMock)
@patch("routers.microsoft_oauth.httpx.AsyncClient")
def test_microsoft_callback_invalid_id_token(
    mock_async_client: MagicMock,
    mock_discovery: AsyncMock,
    oauth_client: TestClient,
) -> None:
    mock_discovery.return_value = _FAKE_DISCO
    mock_async_client.return_value = _mock_token_client()

    state = "valid-state"
    cookie = _state_cookie(state)

    with patch.object(
        oauth_module,
        "_validate_id_token",
        side_effect=HTTPException(status_code=401, detail="id_token invalide."),
    ):
        response = oauth_client.get(
            "/auth/microsoft/callback",
            params={"code": "auth-code", "state": state},
            cookies={oauth_module._OAUTH_STATE_COOKIE: cookie},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "id_token invalide."


@patch.object(oauth_module, "_provision_user", new_callable=AsyncMock)
@patch.object(oauth_module, "_validate_id_token")
@patch.object(oauth_module, "_discovery", new_callable=AsyncMock)
@patch("routers.microsoft_oauth.httpx.AsyncClient")
def test_microsoft_callback_success_new_user(
    mock_async_client: MagicMock,
    mock_discovery: AsyncMock,
    mock_validate: MagicMock,
    mock_provision: AsyncMock,
    oauth_client: TestClient,
) -> None:
    mock_discovery.return_value = _FAKE_DISCO
    mock_async_client.return_value = _mock_token_client()
    mock_validate.return_value = {
        "email": "new.user@school.fr",
        "oid": "azure-oid-123",
        "name": "New User",
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
    }
    mock_provision.return_value = {
        "id_user": 99,
        "email": "new.user@school.fr",
        "auth_provider": "microsoft",
    }

    state = "new-user-state"
    response = oauth_client.get(
        "/auth/microsoft/callback",
        params={"code": "auth-code", "state": state},
        cookies={oauth_module._OAUTH_STATE_COOKIE: _state_cookie(state)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == config.APP_POST_LOGIN_REDIRECT
    assert config.SESSION_COOKIE_NAME in response.cookies
    mock_provision.assert_awaited_once_with("new.user@school.fr", "azure-oid-123", "New User")


@patch.object(oauth_module, "_provision_user", new_callable=AsyncMock)
@patch.object(oauth_module, "_validate_id_token")
@patch.object(oauth_module, "_discovery", new_callable=AsyncMock)
@patch("routers.microsoft_oauth.httpx.AsyncClient")
def test_microsoft_callback_success_existing_user(
    mock_async_client: MagicMock,
    mock_discovery: AsyncMock,
    mock_validate: MagicMock,
    mock_provision: AsyncMock,
    oauth_client: TestClient,
) -> None:
    mock_discovery.return_value = _FAKE_DISCO
    mock_async_client.return_value = _mock_token_client()
    mock_validate.return_value = {
        "preferred_username": "Existing.User@school.fr",
        "oid": "azure-oid-456",
        "name": "Existing User",
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
    }
    mock_provision.return_value = {
        "id_user": 12,
        "email": "existing.user@school.fr",
        "auth_provider": "local",
    }

    state = "existing-user-state"
    response = oauth_client.get(
        "/auth/microsoft/callback",
        params={"code": "auth-code", "state": state},
        cookies={oauth_module._OAUTH_STATE_COOKIE: _state_cookie(state)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    mock_provision.assert_awaited_once_with(
        "existing.user@school.fr", "azure-oid-456", "Existing User"
    )


def test_microsoft_callback_provider_error_redirects_to_login(oauth_client: TestClient) -> None:
    response = oauth_client.get(
        "/auth/microsoft/callback",
        params={"error": "access_denied", "error_description": "User cancelled"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=access_denied" in response.headers["location"]
    assert response.headers["location"].startswith(config.APP_LOGIN_URL)


def test_read_session_without_cookie_returns_401(oauth_client: TestClient) -> None:
    response = oauth_client.get("/auth/session")
    assert response.status_code == 401


def test_read_session_with_valid_cookie(oauth_client: TestClient) -> None:
    token = create_session_token(
        {"id_user": 5, "email": "session@example.com", "auth_provider": "microsoft"}
    )
    response = oauth_client.get("/auth/session", cookies={config.SESSION_COOKIE_NAME: token})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 5
    assert body["email"] == "session@example.com"
    assert body["auth_provider"] == "microsoft"


def test_logout_clears_session_cookie(oauth_client: TestClient) -> None:
    token = create_session_token({"id_user": 1, "email": "a@b.com", "auth_provider": "local"})
    response = oauth_client.post(
        "/auth/logout",
        cookies={config.SESSION_COOKIE_NAME: token},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    set_cookie = response.headers.get("set-cookie", "")
    assert config.SESSION_COOKIE_NAME in set_cookie


def test_validate_id_token_rejects_bad_nonce() -> None:
    with patch.object(oauth_module, "PyJWKClient") as mock_jwks:
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = "secret"
        with patch.object(oauth_module.jwt, "decode", return_value={
            "iss": "https://login.microsoftonline.com/tenant/v2.0",
            "nonce": "other-nonce",
        }):
            with pytest.raises(HTTPException) as exc:
                oauth_module._validate_id_token("token", _FAKE_DISCO, "expected-nonce")
            assert exc.value.status_code == 401
            assert "Nonce" in exc.value.detail
