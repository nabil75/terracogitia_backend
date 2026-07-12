"""Fixtures partagées pour les tests backend."""
from __future__ import annotations

import os

# Variables minimales avant le premier import de `config`.
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-chars")
os.environ.setdefault("MICROSOFT_CLIENT_ID", "test-client-id")
os.environ.setdefault("MICROSOFT_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("MICROSOFT_REDIRECT_URI", "http://localhost:8002/auth/microsoft/callback")
os.environ.setdefault("APP_POST_LOGIN_REDIRECT", "http://localhost:4200/")
os.environ.setdefault("APP_LOGIN_URL", "http://localhost:4200/login")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from routers.microsoft_oauth import router as microsoft_oauth_router


@pytest.fixture
def oauth_client() -> TestClient:
    """Client HTTP limité au router OAuth Microsoft (sans lifespan DB)."""
    app = FastAPI()
    app.include_router(microsoft_oauth_router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def oauth_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Réinitialise la config OAuth avant chaque test."""
    monkeypatch.setattr(config, "MICROSOFT_TENANT_ID", "common")
    monkeypatch.setattr(config, "MICROSOFT_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "MICROSOFT_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(config, "MICROSOFT_REDIRECT_URI", "http://localhost:8002/auth/microsoft/callback")
    monkeypatch.setattr(config, "APP_POST_LOGIN_REDIRECT", "http://localhost:4200/")
    monkeypatch.setattr(config, "APP_LOGIN_URL", "http://localhost:4200/login")
    monkeypatch.setattr(config, "SESSION_SECRET", "test-session-secret-at-least-32-chars")
    monkeypatch.setattr(config, "SESSION_TTL_HOURS", 8)
    monkeypatch.setattr(config, "SESSION_COOKIE_NAME", "tc_session")
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", False)
