"""Session applicative sous forme de jeton signé sans état (JWT HS256).

Introduite pour les connexions OAuth Microsoft. La connexion classique
email/mot de passe reste inchangée (sans session) — cf. change add-microsoft-oauth.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import jwt
from fastapi import Request, Response

import config

_ALG = "HS256"


def _secret() -> str:
    if not config.SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET manquant : gestion de session impossible.")
    return config.SESSION_SECRET


def create_session_token(user: dict[str, Any]) -> str:
    """Émet un jeton de session signé pour l'utilisateur donné."""
    now = int(time.time())
    payload = {
        "sub": str(user["id_user"]),
        "email": user.get("email"),
        "provider": user.get("auth_provider") or "local",
        "iat": now,
        "exp": now + config.SESSION_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALG)


def decode_session_token(token: str) -> Optional[dict[str, Any]]:
    """Décode et vérifie un jeton de session ; renvoie None si invalide/expiré."""
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALG])
    except jwt.PyJWTError:
        return None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        max_age=config.SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=config.SESSION_COOKIE_NAME, path="/")


def get_session_user(request: Request) -> Optional[dict[str, Any]]:
    """Retourne les claims de session si un cookie valide est présent, sinon None."""
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        return None
    return decode_session_token(token)
