"""Authentification Microsoft (OAuth 2.0 / OpenID Connect).

Flux Authorization Code + PKCE orchestré côté serveur (Backend-for-Frontend) :
- `GET /auth/microsoft/login`    : initie le flux et redirige vers Microsoft Entra ID
- `GET /auth/microsoft/callback` : valide l'`id_token`, provisionne/lie le compte, ouvre une session
- `GET /auth/session`            : renvoie l'utilisateur courant si une session valide existe
- `POST /auth/logout`            : invalide la session

Le `state`, le `nonce` et le `code_verifier` PKCE sont conservés dans un cookie
signé de courte durée (approche sans état côté serveur).
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

import config
from queries import postgres_insert_query, postgres_select_query, postgres_update_query
from session_utils import (
    clear_session_cookie,
    create_session_token,
    get_session_user,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_OAUTH_STATE_COOKIE = "tc_oauth_state"
_OAUTH_STATE_TTL = 600  # 10 minutes
_SCOPE = "openid profile email"

_discovery_cache: dict[str, Any] = {}


def _authority() -> str:
    tenant = config.MICROSOFT_TENANT_ID or "common"
    return f"https://login.microsoftonline.com/{tenant}"


def _require_oauth_config() -> None:
    missing = [
        name
        for name, value in (
            ("MICROSOFT_CLIENT_ID", config.MICROSOFT_CLIENT_ID),
            ("MICROSOFT_CLIENT_SECRET", config.MICROSOFT_CLIENT_SECRET),
            ("MICROSOFT_REDIRECT_URI", config.MICROSOFT_REDIRECT_URI),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration OAuth Microsoft manquante : {', '.join(missing)}",
        )
    if not config.SESSION_SECRET:
        raise HTTPException(status_code=500, detail="SESSION_SECRET manquant.")


async def _discovery() -> dict[str, Any]:
    key = _authority()
    if key in _discovery_cache:
        return _discovery_cache[key]
    url = f"{key}/v2.0/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        doc = resp.json()
    _discovery_cache[key] = doc
    return doc


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _encode_state_cookie(data: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {**data, "iat": now, "exp": now + _OAUTH_STATE_TTL}
    return jwt.encode(payload, config.SESSION_SECRET, algorithm="HS256")


def _decode_state_cookie(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, config.SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _fail_redirect(reason: str) -> RedirectResponse:
    sep = "&" if "?" in config.APP_LOGIN_URL else "?"
    resp = RedirectResponse(
        f"{config.APP_LOGIN_URL}{sep}auth_error={reason}", status_code=302
    )
    resp.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    return resp


def _validate_id_token(id_token: str, disco: dict[str, Any], nonce: Optional[str]) -> dict[str, Any]:
    try:
        jwks_client = PyJWKClient(disco["jwks_uri"])
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.MICROSOFT_CLIENT_ID,
            # Avec le tenant `common`, l'`iss` varie selon le tenant : on le vérifie
            # manuellement ci-dessous plutôt que via la validation stricte de PyJWT.
            options={"verify_iss": False},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="id_token invalide.")

    if "login.microsoftonline.com" not in str(claims.get("iss", "")):
        raise HTTPException(status_code=401, detail="Émetteur du jeton non reconnu.")
    if nonce and claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="Nonce du jeton invalide (anti-rejeu).")
    return claims


async def _provision_user(email: str, oid: Optional[str], display_name: Optional[str]) -> dict[str, Any]:
    rows = await postgres_select_query(
        "SELECT id_user, email, auth_provider FROM users WHERE email = $1",
        email,
    )
    if rows:
        user = dict(rows[0])
        await postgres_update_query(
            "UPDATE users SET azure_oid = COALESCE($1, azure_oid), "
            "display_name = COALESCE(display_name, $2) WHERE id_user = $3",
            oid,
            display_name,
            user["id_user"],
        )
        return user

    new_id = await postgres_insert_query(
        "INSERT INTO users (email, auth_provider, azure_oid, display_name) "
        "VALUES ($1, 'microsoft', $2, $3) RETURNING id_user",
        email,
        oid,
        display_name,
    )
    return {"id_user": new_id, "email": email, "auth_provider": "microsoft"}


@router.get("/microsoft/login")
async def microsoft_login():
    """Initie le flux OIDC : génère state/nonce/PKCE et redirige vers Microsoft."""
    _require_oauth_config()
    disco = await _discovery()

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()

    params = {
        "client_id": config.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": config.MICROSOFT_REDIRECT_URI,
        "response_mode": "query",
        "scope": _SCOPE,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{disco['authorization_endpoint']}?{urlencode(params)}"

    resp = RedirectResponse(auth_url, status_code=302)
    resp.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=_encode_state_cookie({"state": state, "nonce": nonce, "cv": verifier}),
        max_age=_OAUTH_STATE_TTL,
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """Traite le retour Microsoft : vérifie state, échange le code, ouvre une session."""
    _require_oauth_config()

    # Erreur renvoyée par Microsoft (ex. consentement refusé).
    if error:
        return _fail_redirect(error)

    saved_cookie = request.cookies.get(_OAUTH_STATE_COOKIE)
    saved = _decode_state_cookie(saved_cookie) if saved_cookie else None
    if not saved or not state or state != saved.get("state"):
        raise HTTPException(status_code=400, detail="État OAuth invalide (anti-CSRF).")
    if not code:
        raise HTTPException(status_code=400, detail="Code d'autorisation manquant.")

    disco = await _discovery()

    token_data = {
        "client_id": config.MICROSOFT_CLIENT_ID,
        "client_secret": config.MICROSOFT_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.MICROSOFT_REDIRECT_URI,
        "code_verifier": saved.get("cv"),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(disco["token_endpoint"], data=token_data)
    if token_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Échec de l'échange du code OAuth.")

    id_token = token_resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="id_token manquant dans la réponse Microsoft.")

    claims = _validate_id_token(id_token, disco, saved.get("nonce"))

    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Aucune adresse email fournie par Microsoft.")
    # Refus si l'email est explicitement marqué non vérifié par Microsoft.
    if claims.get("email_verified") is False:
        raise HTTPException(status_code=401, detail="Adresse email non vérifiée par Microsoft.")

    oid = claims.get("oid") or claims.get("sub")
    display_name = claims.get("name")
    user = await _provision_user(email, oid, display_name)

    token = create_session_token(user)
    resp = RedirectResponse(config.APP_POST_LOGIN_REDIRECT, status_code=302)
    set_session_cookie(resp, token)
    resp.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    return resp


@router.get("/session")
async def read_session(request: Request):
    """Renvoie l'utilisateur courant si une session valide est présente."""
    data = get_session_user(request)
    if not data:
        raise HTTPException(status_code=401, detail="Aucune session active.")
    return {
        "id": int(data["sub"]),
        "email": data.get("email"),
        "auth_provider": data.get("provider"),
    }


@router.post("/logout")
async def logout():
    """Invalide la session en effaçant le cookie."""
    resp = JSONResponse({"ok": True})
    clear_session_cookie(resp)
    return resp
