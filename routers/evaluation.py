
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from openai import OpenAI, RateLimitError
import json
import ast
import re
import openai
from mistralai.client import Mistral
from pydantic import BaseModel

import config
from queries import postgres_insert_query, postgres_select_query

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

client = OpenAI(api_key=config.OPENAI_API_KEY)

class EvaluateResponseRequest(BaseModel):
    subtheme: str
    question: str
    response: str


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
async def evaluate_response(subtheme: str, question: str, response: str):
    return await _evaluate(subtheme, question, response)


@router.post("/evaluate_response")
async def evaluate_response_post(payload: EvaluateResponseRequest):
    return await _evaluate(payload.subtheme, payload.question, payload.response)


async def _evaluate(subtheme: str, question: str, response: str):
    api_key = os.environ["MISTRAL_API_KEY"]
    model = "mistral-large-latest"

    client = Mistral(api_key=api_key)

    prompt = """
                    Tu es un expert en """+subtheme+""". Ton objectif est d'examiner la réponse d'un participant à une question spécifique : """+question+""". Ton analyse doit être factuelle, claire et pédagogique. Elle doit mettre en évidence les points clés à retenir.
                    Voici la réponse du participant : """+response+""".
                    Analyse cette réponse en te basant sur les critères suivants :
                    1. Pertinence : La réponse est-elle pertinente par rapport à la question posée ?
                    2. Précision : La réponse est-elle précise et factuellement correcte ?
                    3. Clarté : La réponse est-elle claire et bien structurée ?
                    4. Points clés : Quels sont les points clés à retenir de cette réponse ?
                    Fournis une analyse détaillée en utilisant ces critères, et souligne les éléments importants que le participant devrait retenir pour améliorer sa compréhension du sujet.
                    En fonction de ton évaluation, donne une note de 0 à 100 à la réponse du participant.
                    IMPORTANT :
                    - Réponds avec du JSON STRICT uniquement.
                    - N'ajoute AUCUN bloc markdown, AUCUN backtick, AUCUN texte avant/après.
                    - La clé "evaluation" doit être un OBJET structuré (pas une chaîne).
                    Fournis ta réponse exactement avec ce format JSON :
                    {
                        "evaluation": {
                            "pertinence": {
                                "analyse": "texte",
                                "note_partielle": 0-100
                            },
                            "precision": {
                                "analyse": "texte",+
                            }
                        },
                        "note": 0-100,
                        "synthese": {
                            "points_forts": ["..."],
                            "points_faibles": ["..."],
                            "conseils_pedagogiques": ["..."]
                        }
                    }
                    """

    chat_response = client.chat.complete(
        model= model,
        messages = [
            {
                "role": "user",
                "content": prompt
            },
        ]
    )

    response_text = chat_response.choices[0].message.content
    # Extraction et affichage du JSON
    try:
        start_index = response_text.index("{")
        end_index = response_text.rindex("}") + 1
        json_content = response_text[start_index:end_index]
        response_json = json.loads(json_content)
        result = {
            "pertinence": response_json["evaluation"]["pertinence"]["analyse"],
            "pertinence_note": response_json["evaluation"]["pertinence"]["note_partielle"],
            "precision": response_json["evaluation"]["precision"]["analyse"],
            "precision_note": response_json["evaluation"]["precision"]["note_partielle"],
            "clarte": response_json["evaluation"]["clarte"]["analyse"],
            "clarte_note": response_json["evaluation"]["clarte"]["note_partielle"],
            "note": response_json["note"],
            "synthese_points_forts": response_json["synthese"]["points_forts"],
            "synthese_points_faibles": response_json["synthese"]["points_faibles"],
            "synthese_conseils_pedagogiques": response_json["synthese"]["conseils_pedagogiques"]
        }
        return result

    except (ValueError, json.JSONDecodeError):
        content="Erreur : Impossible d'extraire le JSON."
    except openai.RateLimitError as e:
        content = "Rate limit reached. Waiting..."

    
    return content


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

