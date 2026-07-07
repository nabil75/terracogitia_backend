import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from queries import postgres_insert_query, postgres_select_query
from config import APP_DATA_DIR

router = APIRouter(prefix="/questions", tags=["questions"])

_DEFAULT_GENSIM_QUESTIONS_CSV = APP_DATA_DIR / "other_data" / "gensim_questions.csv"


def _decode_csv_bytes(raw: bytes) -> str:
    """UTF-8 (avec BOM) si possible, sinon encodages typiques Windows / Excel français."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _normalize_jsonb_value(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _has_dessin_value(raw: Any) -> bool:
    val = _normalize_jsonb_value(raw)
    if val is None:
        return False
    if isinstance(val, dict):
        return len(val) > 0
    if isinstance(val, list):
        return len(val) > 0
    return bool(val)


class QuestionDessinPayload(BaseModel):
    dessin: dict[str, Any] = Field(..., description="JSON Fabric.js (canvas.toObject())")


class QuestionDessinResponse(BaseModel):
    id_question: int
    dessin: Optional[dict[str, Any]] = None
    has_dessin: bool = False


async def _ensure_question_exists(id_question: int) -> None:
    rows = await postgres_select_query(
        "SELECT 1 FROM question WHERE id_question = $1 LIMIT 1",
        id_question,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Question introuvable")


@router.get("/{id_question}/dessin", response_model=QuestionDessinResponse)
async def get_question_dessin(id_question: int):
    """Retourne le dessin JSONB associé à une question (Fabric.js)."""
    rows = await postgres_select_query(
        """
        SELECT id_question, dessin
        FROM question
        WHERE id_question = $1
        """,
        id_question,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Question introuvable")
    row = dict(rows[0])
    dessin = _normalize_jsonb_value(row.get("dessin"))
    if isinstance(dessin, dict):
        pass
    else:
        dessin = None
    return QuestionDessinResponse(
        id_question=id_question,
        dessin=dessin,
        has_dessin=_has_dessin_value(dessin),
    )


@router.put("/{id_question}/dessin", response_model=QuestionDessinResponse)
async def save_question_dessin(id_question: int, body: QuestionDessinPayload):
    """Enregistre ou remplace le dessin d'une question."""
    await _ensure_question_exists(id_question)
    if not isinstance(body.dessin, dict) or not body.dessin:
        raise HTTPException(status_code=400, detail="Corps « dessin » JSON invalide ou vide.")
    rows = await postgres_select_query(
        """
        UPDATE question
        SET dessin = $1::jsonb
        WHERE id_question = $2
        RETURNING id_question, dessin
        """,
        json.dumps(body.dessin, ensure_ascii=False),
        id_question,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Question introuvable")
    dessin = _normalize_jsonb_value(dict(rows[0]).get("dessin"))
    return QuestionDessinResponse(
        id_question=id_question,
        dessin=dessin if isinstance(dessin, dict) else body.dessin,
        has_dessin=True,
    )


@router.delete("/{id_question}/dessin", response_model=QuestionDessinResponse)
async def delete_question_dessin(id_question: int):
    """Supprime le dessin associé à une question."""
    await _ensure_question_exists(id_question)
    rows = await postgres_select_query(
        """
        UPDATE question
        SET dessin = NULL
        WHERE id_question = $1
        RETURNING id_question, dessin
        """,
        id_question,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Question introuvable")
    return QuestionDessinResponse(
        id_question=id_question,
        dessin=None,
        has_dessin=False,
    )


async def insert_gensim_questions_from_csv(
    csv_path: Optional[Path] = None,
    *,
    id_subtheme: Optional[int] = None,
    question_type: str = "ouverte",
) -> dict:
    """
    Lit ``gensim_questions.csv`` (une ligne = une question ; première colonne CSV = libellé)
    et insère chaque ligne non vide dans la table ``question``.
    """
    path = csv_path if csv_path is not None else _DEFAULT_GENSIM_QUESTIONS_CSV
    if not path.is_file():
        raise FileNotFoundError(str(path))

    inserted = 0
    skipped = 0

    raw = path.read_bytes()
    text = _decode_csv_bytes(raw)
    reader = csv.reader(StringIO(text))
    for row in reader:
        if not row:
            skipped += 1
            continue
        libelle = (row[0] or "").strip()
        if not libelle:
            skipped += 1
            continue
        await postgres_insert_query(
            """
            INSERT INTO question (libelle, type, id_subtheme)
            VALUES ($1, $2, $3)
            RETURNING id_question
            """,
            libelle,
            question_type,
            163,
        )
        inserted += 1

    return {"inserted": inserted, "skipped": skipped}


@router.put("/insert_questions/{id_subtheme}")
async def insert_questions(id_subtheme: int):
    try:
        return await insert_gensim_questions_from_csv(id_subtheme=id_subtheme)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
