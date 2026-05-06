"""
Routeur disciplines.

Une discipline est le niveau **au-dessus** du thème : elle regroupe plusieurs thèmes.
Schéma SQL attendu (cf. fix_theme_sequences.sql / migration ajoutée) :

    CREATE TABLE discipline (
        id_discipline SERIAL PRIMARY KEY,
        label TEXT NOT NULL,
        description TEXT
    );

    ALTER TABLE theme
        ADD COLUMN IF NOT EXISTS id_discipline INTEGER
        REFERENCES discipline(id_discipline) ON DELETE SET NULL;
"""

import json
import os

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel, Field
from typing import List, Optional

import database
from queries import postgres_select_query
from routers.theme import _mistral_message_content_to_text, _parse_json_object_from_llm_content

router = APIRouter(prefix="/disciplines", tags=["disciplines"])


class Discipline(BaseModel):
    id_discipline: int
    label: str
    description: Optional[str] = None

class CreateDisciplinePayload(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


@router.get("/all_disciplines", response_model=List[Discipline])
async def get_all_disciplines():
    """
    Retourne la liste des disciplines triée par id pour avoir un ordre déterministe.
    Le front s'en sert pour afficher la popup de sélection.
    """
    try:
        rows = await postgres_select_query(
            """
            SELECT id_discipline, label, description
            FROM discipline
            ORDER BY id_discipline
            """
        )
        return [
            Discipline(
                id_discipline=row["id_discipline"],
                label=row["label"],
                description=row["description"],
            )
            for row in rows
        ]
    except Exception as e:
        print("ERROR get_all_disciplines:", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create_discipline")
async def create_discipline(payload: CreateDisciplinePayload):
    label = payload.label.strip()
    description = (payload.description or "").strip() or None
    discipline_description_for_ai = description or ""

    themes_data = await _generate_list_themes_ai(label, discipline_description_for_ai)
    if isinstance(themes_data, str):
        raise HTTPException(status_code=502, detail=themes_data)

    if database.pool is None:
        raise HTTPException(
            status_code=500, detail="Pool base de données non initialisé."
        )

    created_themes: List[dict] = []
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            new_id = await conn.fetchval(
                """
                INSERT INTO discipline (label, description)
                VALUES ($1, $2)
                RETURNING id_discipline
                """,
                label,
                description,
            )
            for item in themes_data:
                theme_id = await conn.fetchval(
                    """
                    INSERT INTO theme (label, tagline, description, id_discipline)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id_theme
                    """,
                    item["label"],
                    "",
                    item.get("description") or "",
                    new_id,
                )
                created_themes.append(
                    {
                        "id_theme": theme_id,
                        "label": item["label"],
                        "tagline": "",
                        "description": item.get("description") or "",
                    }
                )

    return {
        "id_discipline": new_id,
        "label": label,
        "description": description,
        "themes": created_themes,
    }

async def _generate_list_themes_ai(discipline_label: str, discipline_description: str):
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."

    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"

    prompt = """
            Tu es un expert en pédagogie et en structuration de parcours d’apprentissage.
            Ta mission est de définir les principaux thèmes nécessaires pour maîtriser la discipline suivante :
            Nom de la discipline : """+discipline_label+"""
            Description de la discipline : """+discipline_description+"""

            Génère environ 10 thèmes couvrant l’ensemble des connaissances essentielles, des bases aux concepts avancés.

            Pour chaque thème :

            Fournis un label court (2 à 5 mots maximum)
            Rédige une description concise (1 à 3 phrases) expliquant les compétences ou connaissances acquises

            Les thèmes doivent être :

            Cohérents avec la description fournie
            Organisés selon une progression pédagogique logique (du fondamental au plus avancé)
            Non redondants
            Suffisamment complets pour couvrir la discipline

            Contraintes de sortie :
            Réponds uniquement en JSON valide. Ne fournis aucun texte en dehors du JSON.
            Respecte strictement le format suivant (objet racine obligatoire pour le mode JSON du modèle) :
            {
                "themes": [
                    {
                        "label": "...",
                        "description": "..."
                    }
                ]
            }

        """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 400 and payload.get("response_format"):
                payload_fallback = {
                    k: v for k, v in payload.items() if k != "response_format"
                }
                response = await client.post(
                    url, headers=headers, json=payload_fallback
                )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return f"Erreur : réponse Mistral sans choices. Réponse : {str(data)[:800]}"
            message = (choices[0] or {}).get("message") or {}
            response_text = _mistral_message_content_to_text(message.get("content"))
            if not response_text.strip():
                return (
                    f"Erreur : pas de contenu dans la réponse. Réponse : {str(data)[:800]}"
                )

            response_json = _parse_json_object_from_llm_content(response_text)
            themes_raw = response_json.get("themes")
            if not isinstance(themes_raw, list):
                return (
                    "Erreur : le JSON doit contenir une clé "
                    "\"themes\" avec un tableau d'objets {label, description}."
                )

            themes_out = []
            for item in themes_raw:
                if not isinstance(item, dict):
                    continue
                label = (item.get("label") or "").strip()
                description = (item.get("description") or "").strip()
                if label:
                    themes_out.append(
                        {"label": label, "description": description or ""}
                    )

            if not themes_out:
                return (
                    "Erreur : aucun thème exploitable (labels vides ou structure invalide)."
                )
            return themes_out

    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        return f"Erreur API Mistral (HTTP {e.response.status_code}) : {snippet}"
    except (ValueError, json.JSONDecodeError) as e:
        return f"Erreur : impossible d'extraire le JSON ({str(e)})."
    except httpx.TimeoutException:
        return "Erreur : timeout de la requête vers Mistral (délai dépassé)."
    except Exception as e:
        print("ERROR _generate_list_themes_ai:", repr(e))
        return f"Erreur : {str(e)}"
