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
