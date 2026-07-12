from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Fichier local hors dépôt (clés sensibles Mistral).
_DEFAULT_MISTRAL_SECRETS_ENV = Path(r"C:\Users\LG\Documents\data_terracogitia\data_key\.env")

# Données applicatives hors dépôt (audio, médias Discover, CSV, …).
_DEFAULT_APP_DATA_DIR = Path(r"C:\Users\LG\Documents\data_terracogitia\data")


def app_data_dir() -> Path:
    raw = (os.environ.get("APP_DATA_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_APP_DATA_DIR


APP_DATA_DIR = app_data_dir()


def _mistral_secrets_env_path() -> Path:
    raw = (os.environ.get("MISTRAL_SECRETS_ENV") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_MISTRAL_SECRETS_ENV


def load_app_env() -> None:
    """Charge le .env du projet puis le .env Mistral externe (prioritaire pour MISTRAL_API_KEY)."""
    load_dotenv()
    mistral_env = _mistral_secrets_env_path()
    if mistral_env.is_file():
        load_dotenv(mistral_env, override=True)


load_app_env()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("La clé OPENAI_API_KEY est manquante dans le fichier .env")


# --- Authentification Microsoft (OAuth 2.0 / OpenID Connect) ---------------
# Ces valeurs sont optionnelles au démarrage : leur absence n'empêche pas le
# lancement de l'app, mais les endpoints /auth/microsoft/* renverront 500 tant
# que la configuration est incomplète.
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI")

# URLs frontend de retour après le flux OAuth.
APP_POST_LOGIN_REDIRECT = os.getenv("APP_POST_LOGIN_REDIRECT", "http://localhost:4200/home")
APP_LOGIN_URL = os.getenv("APP_LOGIN_URL", "http://localhost:4200/login")

# --- Session applicative (cookie signé sans état) --------------------------
SESSION_SECRET = os.getenv("SESSION_SECRET")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "8"))
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "tc_session")
# `Secure` par défaut ; désactivable en dev via SESSION_COOKIE_SECURE=false.
SESSION_COOKIE_SECURE = (os.getenv("SESSION_COOKIE_SECURE", "true").strip().lower() != "false")
