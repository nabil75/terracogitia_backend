
import os
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from openai import OpenAI, RateLimitError
import json
import ast
import re
import openai
from mistralai.client import Mistral
from pydantic import BaseModel

import config
from mistral.evaluation_mistral import evaluate_response_with_mistral
from mistral.language_prompts import normalize_lang
from queries import postgres_insert_query, postgres_select_query

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

client = OpenAI(api_key=config.OPENAI_API_KEY)

class EvaluateResponseRequest(BaseModel):
    subtheme: str
    question: str
    response: str
    lang: Optional[Literal["fr", "en"]] = None


class StoreEvaluationPayload(BaseModel):
    id_theme: int
    id_subtheme: int
    id_question: int
    reponse: str
    pertinence: str
    pertinence_note: Optional[int] = None
    precision: str
    precision_note: Optional[int] = None
    clarte: str
    clarte_note: Optional[int] = None
    synthese_points_forts: List[str]
    synthese_points_faibles: List[str]
    synthese_conseils_pedagogiques: List[str]
    note: Optional[int] = None


def _as_postgres_text_array(value) -> List[str]:
    """Valeur exploitable par asyncpg en colonne PostgreSQL text[]."""
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except json.JSONDecodeError:
                pass
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value]
    return [str(value)]


def _normalize_evaluation_row(r) -> dict:
    d = dict(r)
    for key in (
        "synthese_points_forts",
        "synthese_points_faibles",
        "synthese_conseils_pedagogiques",
    ):
        v = d.get(key)
        if v is None:
            d[key] = []
        elif not isinstance(v, list):
            d[key] = list(v)
    return d


@router.post("/store_evaluation", status_code=201)
async def store_evaluation(payload: StoreEvaluationPayload):
    query = """
    INSERT INTO evaluation (
        id_theme, id_subtheme, id_question, reponse,
        pertinence, pertinence_note, precision, precision_note,
        clarte, clarte_note,
        synthese_points_forts, synthese_points_faibles, synthese_conseils_pedagogiques,
        note
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::text[], $12::text[], $13::text[], $14)
    RETURNING id_evaluation;
    """
    try:
        new_id = await postgres_insert_query(
            query,
            payload.id_theme,
            payload.id_subtheme,
            payload.id_question,
            payload.reponse,
            payload.pertinence,
            payload.pertinence_note,
            payload.precision,
            payload.precision_note,
            payload.clarte,
            payload.clarte_note,
            _as_postgres_text_array(payload.synthese_points_forts),
            _as_postgres_text_array(payload.synthese_points_faibles),
            _as_postgres_text_array(payload.synthese_conseils_pedagogiques),
            payload.note
        )
        return {"id_evaluation": new_id}
    except Exception as e:
        print("ERROR store_evaluation:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_evaluations_by_question/{id_question}")
async def get_evaluations_by_question(id_question: int):
    query = """
    SELECT
        id_evaluation AS id,
        id_theme,
        id_subtheme,
        id_question,
        reponse,
        pertinence,
        pertinence_note,
        precision,
        precision_note,
        clarte,
        clarte_note,
        synthese_points_forts,
        synthese_points_faibles,
        synthese_conseils_pedagogiques,
        note
    FROM evaluation
    WHERE id_question = $1
    ORDER BY id_evaluation DESC
    """
    try:
        rows = await postgres_select_query(query, id_question)
    except Exception as e:
        print("ERROR get_evaluations_by_question:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return [_normalize_evaluation_row(r) for r in rows]


@router.get("/all")
async def get_all_evaluations():
    query = """
    SELECT
        id_evaluation AS id,
        id_theme,
        id_subtheme,
        id_question,
        reponse,
        pertinence,
        pertinence_note,
        precision,
        precision_note,
        clarte,
        clarte_note,
        synthese_points_forts,
        synthese_points_faibles,
        synthese_conseils_pedagogiques,
        note,
        date_creation
    FROM evaluation
    ORDER BY id_evaluation DESC
    """
    try:
        rows = await postgres_select_query(query)
    except Exception as e:
        print("ERROR get_all_evaluations:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return [_normalize_evaluation_row(r) for r in rows]


@router.get("/stats_by_subtheme")
async def get_stats_by_subtheme():
    """
    Agrégats par parcours (id_theme, id_subtheme) utilisés par le tableau de bord Angular.
    Le frontend attend la structure `SubThemeStats` (api.service.ts) :
      - id_theme, id_subtheme, evaluation_count
      - avg_note, avg_pertinence, avg_precision, avg_clarte
      - min_note, max_note
    """
    query = """
    SELECT
        e.id_theme,
        e.id_subtheme,
        COUNT(*)::int                                AS evaluation_count,
        ROUND(AVG(e.note)::numeric, 2)               AS avg_note,
        ROUND(AVG(e.pertinence_note)::numeric, 2)    AS avg_pertinence,
        ROUND(AVG(e.precision_note)::numeric, 2)     AS avg_precision,
        ROUND(AVG(e.clarte_note)::numeric, 2)        AS avg_clarte,
        MIN(e.note)                                  AS min_note,
        MAX(e.note)                                  AS max_note
    FROM evaluation e
    GROUP BY e.id_theme, e.id_subtheme
    ORDER BY e.id_theme, e.id_subtheme
    """
    try:
        rows = await postgres_select_query(query)
    except Exception as e:
        print("ERROR get_stats_by_subtheme:", e)
        raise HTTPException(status_code=500, detail=str(e))

    numeric_keys = (
        "avg_note",
        "avg_pertinence",
        "avg_precision",
        "avg_clarte",
        "min_note",
        "max_note",
    )
    out = []
    for r in rows:
        d = dict(r)
        for key in numeric_keys:
            v = d.get(key)
            d[key] = float(v) if v is not None else None
        out.append(d)
    return out


@router.get("/evaluate_response/{subtheme}/{question}/{response}")
async def evaluate_response(
    subtheme: str,
    question: str,
    response: str,
    lang: Optional[str] = None,
):
    return await _evaluate(subtheme, question, response, lang)


@router.post("/evaluate_response")
async def evaluate_response_post(payload: EvaluateResponseRequest):
    return await _evaluate(
        payload.subtheme,
        payload.question,
        payload.response,
        payload.lang,
    )


async def _evaluate(
    subtheme: str,
    question: str,
    response: str,
    lang: str | None = None,
):
    return await evaluate_response_with_mistral(
        subtheme,
        question,
        response,
        normalize_lang(lang),
    )


@router.get("/{id_evaluation}")
async def get_evaluation_by_id(id_evaluation: int):
    query = """
    SELECT
        id_evaluation AS id,
        id_theme,
        id_subtheme,
        id_question,
        reponse,
        pertinence,
        pertinence_note,
        precision,
        precision_note,
        clarte,
        clarte_note,
        synthese_points_forts,
        synthese_points_faibles,
        synthese_conseils_pedagogiques,
        note
    FROM evaluation
    WHERE id_evaluation = $1
    """
    try:
        rows = await postgres_select_query(query, id_evaluation)
    except Exception as e:
        print("ERROR get_evaluation_by_id:", e)
        raise HTTPException(status_code=500, detail=str(e))
    if not rows:
        raise HTTPException(status_code=404, detail="Évaluation introuvable")
    return _normalize_evaluation_row(rows[0])

