from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

from queries import postgres_insert_query, postgres_select_query, postgres_update_query


router = APIRouter(prefix="/auth", tags=["auth"])


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class ResetPasswordPayload(BaseModel):
    email: EmailStr
    new_password: str = Field(min_length=6)


class AuthErrorCode:
    EMAIL_NOT_FOUND = "email_not_found"
    INVALID_PASSWORD = "invalid_password"
    EMAIL_ALREADY_EXISTS = "email_already_exists"


def _auth_error(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    """
    HTTPException dont le `detail` est un dict structuré ({code, message})
    afin que le frontend puisse discriminer la nature de l'erreur.
    """
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


async def _find_user_by_email(email: str):
    rows = await postgres_select_query(
        "SELECT id_user, email, hashed_password FROM users WHERE email = $1",
        email,
    )
    return rows[0] if rows else None


@router.post("/register", response_model=Dict[str, Any])
async def register_user(payload: RegisterPayload):
    """Crée un utilisateur. Renvoie une erreur si l'email est déjà utilisé."""
    existing = await _find_user_by_email(payload.email)
    if existing is not None:
        raise _auth_error(
            AuthErrorCode.EMAIL_ALREADY_EXISTS,
            "Un compte existe déjà avec cet email.",
            http_status=status.HTTP_409_CONFLICT,
        )

    try:
        new_id = await postgres_insert_query(
            """
            INSERT INTO users (email, hashed_password)
            VALUES ($1, $2)
            RETURNING id_user
            """,
            payload.email,
            hash_password(payload.password),
        )
    except Exception as e:
        print("ERROR register_user:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "id": new_id, "email": payload.email}


@router.post("/login", response_model=Dict[str, Any])
async def login(payload: LoginPayload):
    """
    - Email inconnu   → 404, detail.code = "email_not_found"
    - Mot de passe KO → 401, detail.code = "invalid_password"
    - Succès          → {ok: True, id, email}
    """
    user = await _find_user_by_email(payload.email)
    if user is None:
        raise _auth_error(
            AuthErrorCode.EMAIL_NOT_FOUND,
            "Aucun compte n'est associé à cet email.",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    if not verify_password(payload.password, user["hashed_password"]):
        raise _auth_error(
            AuthErrorCode.INVALID_PASSWORD,
            "Mot de passe incorrect.",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    return {"ok": True, "id": user["id_user"], "email": user["email"]}


@router.post("/reset_password", response_model=Dict[str, Any])
async def reset_password(payload: ResetPasswordPayload):
    """
    - Email inconnu → 404, detail.code = "email_not_found"
    - Succès        → {ok: True, email}
    """
    user = await _find_user_by_email(payload.email)
    if user is None:
        raise _auth_error(
            AuthErrorCode.EMAIL_NOT_FOUND,
            "Aucun compte n'est associé à cet email.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    try:
        await postgres_update_query(
            "UPDATE users SET hashed_password = $1 WHERE email = $2",
            hash_password(payload.new_password),
            payload.email,
        )
    except Exception as e:
        print("ERROR reset_password:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "email": payload.email}
