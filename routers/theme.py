import asyncio
import os
import httpx
from pathlib import Path
import shutil
from unittest import result
from fastapi import APIRouter, File, HTTPException, UploadFile
from typing import List
import whisper
import json
from io import StringIO
from openai import BaseModel
from pydantic import AliasChoices, BaseModel as PydanticBaseModel, ConfigDict, Field
from uuid import uuid4
from queries import *
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional
from models import Theme, SubTheme
from fastapi import HTTPException
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker
from mistralai.client import Mistral

router = APIRouter(prefix="/themes", tags=["themes"])
# Routes attendues par le front sans préfixe /themes (ex. PUT /subthemes/27)
subthemes_router = APIRouter(prefix="/subthemes", tags=["subthemes"])

DEFAULT_AI_QUESTION_TYPE = "ouverte"

model = whisper.load_model("base")
DATA_DIR = Path("data/audio")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Modèle Pydantic pour la réponse
class SubTheme(BaseModel):
    id: int
    label: str
    description: str

class Theme(BaseModel):
    id: int
    label: str
    tagline: str
    description: str
    subThemes: List[SubTheme]

class SubThemeCreatePayload(PydanticBaseModel):
    model_config = ConfigDict(populate_by_name=True)
    label: str
    description: str

class CreateThemePayload(PydanticBaseModel):
    model_config = ConfigDict(populate_by_name=True)
    label: str
    tagline: str
    description: str
    sub_themes: List[SubThemeCreatePayload] = Field(
        default_factory=list, alias="subThemes"
    )

class UpdateThemePayload(PydanticBaseModel):
    model_config = ConfigDict(populate_by_name=True)
    label: str
    tagline: str
    description: str


class CreateSubThemePayload(PydanticBaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id_theme: int = Field(
        ...,
        validation_alias=AliasChoices("idTheme", "id_theme", "themeId"),
    )
    label: str
    description: str

class Context(BaseModel):
    label: Optional[str] = None
    content: str


def _question_libelle_from_ai_entry(entry) -> Optional[str]:
    if entry is None:
        return None
    if isinstance(entry, str):
        s = entry.strip()
        return s or None
    if isinstance(entry, dict):
        for v in entry.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    s = str(entry).strip()
    return s or None


def _iter_domaine_questions(questions_raw):
    if questions_raw is None:
        return
    if isinstance(questions_raw, dict):
        for item in questions_raw.values():
            yield item
    elif isinstance(questions_raw, list):
        for item in questions_raw:
            yield item

async def _create_subtheme_row(
    id_theme: int, label: str, description: str
) -> SubTheme:
    exists = await postgres_select_query(
        "SELECT 1 FROM theme WHERE id_theme = $1 LIMIT 1",
        id_theme,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Thème introuvable")

    sub_id = await postgres_insert_query(
        """
        INSERT INTO subtheme (id_theme, label, description)
        VALUES ($1, $2, $3)
        RETURNING id_subtheme
        """,
        id_theme,
        label,
        description,
    )
    return SubTheme(
        id=sub_id,
        label=label,
        description=description,
    )


async def _get_theme_by_id(theme_id: int) -> Theme:
    query = """
    SELECT
        t.id_theme AS id,
        t.label,
        t.tagline,
        t.description,
        COALESCE(
            json_agg(
                json_build_object(
                    'id', s.id_subtheme,
                    'label', s.label,
                    'description', s.description
                )
            ) FILTER (WHERE s.id_subtheme IS NOT NULL),
            '[]'::json
        ) AS "subThemes"
    FROM theme t
    LEFT JOIN subtheme s ON s.id_theme = t.id_theme
    WHERE t.id_theme = $1
    GROUP BY t.id_theme, t.label, t.tagline, t.description
    """
    rows = await postgres_select_query(query, theme_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Thème introuvable")
    row = dict(rows[0])
    data = row.get("subThemes") or row.get("subthemes")
    if isinstance(data, str):
        data = json.loads(data)
    if not data:
        data = []
    subthemes = [
        SubTheme(id=s["id"], label=s["label"], description=s["description"])
        for s in data
    ]
    return Theme(
        id=row["id"],
        label=row["label"],
        tagline=row["tagline"],
        description=row["description"],
        subThemes=subthemes,
    )


@router.post("/get_transcribe_audio")
async def get_transcribe_audio(audio: UploadFile = File(...)):
    
    # 1️⃣ fichier temporaire
    temp_path = Path(f"temp_{uuid4()}.webm")

    with temp_path.open("wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    # 2️⃣ id unique définitif
    audio_id = uuid4()
    final_path = DATA_DIR / f"{audio_id}.webm"

    try:
        # 3️⃣ transcription
        result = model.transcribe(str(temp_path), language="fr")
        text = result["text"]

        # 4️⃣ sauvegarde définitive
        shutil.move(str(temp_path), final_path)

    finally:
        # 5️⃣ sécurité si une erreur survient
        if temp_path.exists():
            temp_path.unlink()

    return {
        "id": str(audio_id),
        "text": text
    }

@router.get("/get_audio_file/{id_audio}")
def get_audio(id_audio: str):

    audio_path = DATA_DIR / f"{id_audio}.webm"

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio introuvable")

    return FileResponse(
        path=audio_path,
        media_type="audio/webm",
        filename=f"{id_audio}.webm"
    )

@router.get("/all_themes", response_model=List[Theme])
async def get_all_themes(id_discipline: Optional[int] = None):
    """
    Liste des thèmes (avec leurs sous-thèmes), filtrable par discipline.
    `id_discipline` est optionnel : sans paramètre, tous les thèmes sont retournés
    (compat. arrière). Avec paramètre, seuls les thèmes rattachés à cette discipline
    sont remontés (`theme.id_discipline = $1`).
    """
    try :
        # On préfère un placeholder optionnel à de la concaténation ; `IS NOT DISTINCT FROM`
        # n'est pas pratique ici — un simple `WHERE` conditionnel suffit.
        if id_discipline is None:
            query = """
                SELECT json_agg(theme_data)
                FROM (
                    SELECT
                        t.id_theme AS id,
                        t.label,
                        t.tagline,
                        t.description,
                        COALESCE(
                            json_agg(
                                json_build_object(
                                    'id', s.id_subtheme,
                                    'label', s.label,
                                    'description', s.description
                                )
                            ) FILTER (WHERE s.id_subtheme IS NOT NULL),
                            '[]'::json
                        ) AS "subThemes"
                    FROM theme t
                    LEFT JOIN subtheme s ON s.id_theme = t.id_theme
                    GROUP BY t.id_theme, t.label, t.tagline, t.description
                    ORDER BY t.id_theme
                ) theme_data;
            """
            result = await postgres_select_query(query)
        else:
            query = """
                SELECT json_agg(theme_data)
                FROM (
                    SELECT
                        t.id_theme AS id,
                        t.label,
                        t.tagline,
                        t.description,
                        COALESCE(
                            json_agg(
                                json_build_object(
                                    'id', s.id_subtheme,
                                    'label', s.label,
                                    'description', s.description
                                )
                            ) FILTER (WHERE s.id_subtheme IS NOT NULL),
                            '[]'::json
                        ) AS "subThemes"
                    FROM theme t
                    LEFT JOIN subtheme s ON s.id_theme = t.id_theme
                    WHERE t.id_discipline = $1
                    GROUP BY t.id_theme, t.label, t.tagline, t.description
                    ORDER BY t.id_theme
                ) theme_data;
            """
            result = await postgres_select_query(query, id_discipline)

        data = result[0]["json_agg"]

        # Sécurité : si c’est une string
        if isinstance(data, str):
            data = json.loads(data)

        return data or []

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_theme", response_model=Theme)
async def create_theme(payload: CreateThemePayload):
    try:
        theme_id = await postgres_insert_query(
            """
            INSERT INTO theme (label, tagline, description)
            VALUES ($1, $2, $3)
            RETURNING id_theme
            """,
            payload.label,
            payload.tagline,
            payload.description,
        )
        created_subthemes: List[SubTheme] = []
        for st in payload.sub_themes:
            sub_id = await postgres_insert_query(
                """
                INSERT INTO subtheme (id_theme, label, description)
                VALUES ($1, $2, $3)
                RETURNING id_subtheme
                """,
                theme_id,
                st.label,
                st.description,
            )
            created_subthemes.append(
                SubTheme(id=sub_id, label=st.label, description=st.description)
            )
        return Theme(
            id=theme_id,
            label=payload.label,
            tagline=payload.tagline,
            description=payload.description,
            subThemes=created_subthemes,
        )
    except Exception as e:
        print("ERROR create_theme:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_subtheme", response_model=SubTheme)
async def create_subtheme(payload: CreateSubThemePayload):
    try:
        return await _create_subtheme_row(
            payload.id_theme,
            payload.label,
            payload.description,
        )
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR create_subtheme:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{theme_id}", response_model=Theme)
async def update_theme(theme_id: int, body: UpdateThemePayload):
    try:
        updated = await postgres_select_query(
            """
            UPDATE theme
            SET label = $1, tagline = $2, description = $3
            WHERE id_theme = $4
            RETURNING id_theme
            """,
            body.label,
            body.tagline,
            body.description,
            theme_id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Thème introuvable")
        return await _get_theme_by_id(theme_id)
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR update_theme:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{theme_id}/subthemes", response_model=SubTheme)
async def create_subtheme_nested(
    theme_id: int, body: SubThemeCreatePayload
):
    """Même logique que create_subtheme ; chemin attendu par le front REST (`POST /themes/{id}/subthemes`)."""
    try:
        return await _create_subtheme_row(
            theme_id, body.label, body.description
        )
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR create_subtheme (nested):", e)
        raise HTTPException(status_code=500, detail=str(e))


# Suppression d'un thème (formation) : DELETE /themes/{id}
# Suppression d'un parcours : DELETE /themes/subthemes/{id}
@router.delete("/subthemes/{subtheme_id}", status_code=204)
async def delete_subtheme_by_id(subtheme_id: int):
    """Supprime un parcours par id seul (DELETE /themes/subthemes/{id})."""
    try:
        rows = await postgres_select_query(
            """
            DELETE FROM subtheme
            WHERE id_subtheme = $1
            RETURNING id_subtheme
            """,
            subtheme_id,
        )
        if not rows:
            raise HTTPException(
                status_code=404, detail="Parcours (sous-thème) introuvable"
            )
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR delete_subtheme_by_id:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{theme_id}", status_code=204)
async def delete_theme(theme_id: int):
    try:
        await postgres_delete_query(
            "DELETE FROM theme WHERE id_theme = $1",
            theme_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/getQuestionsBySubTheme/{subtheme_id}")
async def getQuestionsBySubTheme(subtheme_id: int):
    try:
        rows = await postgres_select_query(
            """
            SELECT
                q.*,
                COALESCE(ev.nombre_evaluations, 0)::int AS nombre_evaluations
            FROM question q
            LEFT JOIN (
                SELECT id_question, COUNT(*) AS nombre_evaluations
                FROM evaluation
                GROUP BY id_question
            ) ev ON ev.id_question = q.id_question
            WHERE q.id_subtheme = $1
            """,
            subtheme_id,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@subthemes_router.put("/{subtheme_id}", response_model=SubTheme)
async def update_subtheme(
    subtheme_id: int, body: SubThemeCreatePayload
):
    """
    Mise à jour d'un parcours (sous-thème) — `PUT /subthemes/{id}`.
    Même shape de corps qu'à la création : label, description.
    """
    try:
        rows = await postgres_select_query(
            """
            UPDATE subtheme
            SET label = $1, description = $2
            WHERE id_subtheme = $3
            RETURNING id_subtheme, label, description
            """,
            body.label,
            body.description,
            subtheme_id,
        )
        if not rows:
            raise HTTPException(
                status_code=404, detail="Parcours (sous-thème) introuvable"
            )
        r = rows[0]
        return SubTheme(
            id=r["id_subtheme"],
            label=r["label"],
            description=r["description"],
        )
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR update_subtheme:", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate_theme", response_model=Theme)
async def generate_theme(payload: CreateThemePayload):
    try:
        theme_id = await postgres_insert_query(
            """
            INSERT INTO theme (label, tagline, description)
            VALUES ($1, $2, $3)
            RETURNING id_theme
            """,
            payload.label,
            payload.tagline,
            payload.description,
        )
        created_subthemes: List[SubTheme] = []
        for st in payload.sub_themes:
            sub_id = await postgres_insert_query(
                """
                INSERT INTO subtheme (id_theme, label, description)
                VALUES ($1, $2, $3)
                RETURNING id_subtheme
                """,
                theme_id,
                st.label,
                st.description,
            )
            created_subthemes.append(
                SubTheme(id=sub_id, label=st.label, description=st.description)
            )
        return Theme(
            id=theme_id,
            label=payload.label,
            tagline=payload.tagline,
            description=payload.description,
            subThemes=created_subthemes,
        )
    except Exception as e:
        print("ERROR create_theme:", e)
        raise HTTPException(status_code=500, detail=str(e))


async def _persist_domaines_under_theme(theme_id: int, domaines: list) -> None:
    """Crée parcours (sous-thèmes) et questions pour un thème existant — même logique que l’extraction IA standard."""
    for dom in domaines:
        if not isinstance(dom, dict):
            continue
        sub_lab = (dom.get("titre") or dom.get("label") or "").strip()
        sub_desc = (dom.get("description") or "").strip()
        if not sub_lab:
            continue
        sub_id = await postgres_insert_query(
            """
            INSERT INTO subtheme (id_theme, label, description)
            VALUES ($1, $2, $3)
            RETURNING id_subtheme
            """,
            theme_id,
            sub_lab,
            sub_desc,
        )
        for q in _iter_domaine_questions(dom.get("questions")):
            libelle = _question_libelle_from_ai_entry(q)
            if not libelle:
                continue
            await postgres_insert_query(
                """
                INSERT INTO question (libelle, type, id_subtheme)
                VALUES ($1, $2, $3)
                RETURNING id_question
                """,
                libelle,
                DEFAULT_AI_QUESTION_TYPE,
                sub_id,
            )


async def _persist_generated_theme_from_ai(ai_payload: dict) -> Theme:
    """Enregistre en base un JSON de thème généré (label, tagline, description, domaines → subthemes + questions)."""
    label = (ai_payload.get("label") or "").strip()
    tagline = (ai_payload.get("tagline") or "").strip()
    description = (ai_payload.get("description") or "").strip()
    domaines = ai_payload.get("domaines") or []

    if not label:
        raise HTTPException(
            status_code=400,
            detail="Thème généré invalide : titre (label) manquant.",
        )

    theme_id = await postgres_insert_query(
        """
        INSERT INTO theme (label, tagline, description)
        VALUES ($1, $2, $3)
        RETURNING id_theme
        """,
        label,
        tagline,
        description,
    )

    await _persist_domaines_under_theme(theme_id, domaines)
    return await _get_theme_by_id(theme_id)


def _theme_row_to_ai_context(row: dict) -> str:
    """Construit le texte de contexte Mistral à partir d’une ligne thème en base."""
    parts: List[str] = []
    lab = (row.get("label") or "").strip()
    if lab:
        parts.append(lab)
    tag = (row.get("tagline") or "").strip()
    if tag:
        parts.append(tag)
    desc = (row.get("description") or "").strip()
    if desc:
        parts.append(desc)
    return ". ".join(parts)


async def generate_parcours_and_questions_from_theme(theme_id: int) -> Theme:
    """
    À partir d’un thème déjà en base (ex. squelette issu d’une discipline),
    appelle l’IA puis enregistre domaines → sous-thèmes + questions sur ce même id_theme.
    """
    rows = await postgres_select_query(
        """
        SELECT id_theme, label, tagline, description
        FROM theme
        WHERE id_theme = $1
        """,
        theme_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Thème introuvable")
    row = dict(rows[0])
    context = _theme_row_to_ai_context(row)
    if not context.strip():
        raise HTTPException(
            status_code=400,
            detail="Thème sans contenu exploitable pour l'IA (label / description vides).",
        )

    raw = await _generate_theme_ai(context)
    if isinstance(raw, str):
        raise HTTPException(status_code=502, detail=raw)

    domaines = raw.get("domaines") or []
    await _persist_domaines_under_theme(theme_id, domaines)
    return await _get_theme_by_id(theme_id)


def _strip_markdown_json_fence(text: str) -> str:
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().rstrip("`").strip() == "":
        lines = lines[:-1]
    elif lines and lines[-1].strip().endswith("```"):
        lines[-1] = lines[-1].strip()[:-3].rstrip()
    return "\n".join(lines).strip()


def _parse_json_object_from_llm_content(content: str) -> dict:
    """Extrait le premier objet JSON de la réponse LLM (gère ```json et chaînes avec accolades)."""
    text = _strip_markdown_json_fence(content)
    start = text.find("{")
    if start == -1:
        raise ValueError("Aucun objet JSON dans la réponse du modèle.")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text, start)
    if not isinstance(obj, dict):
        raise ValueError("Le JSON racine doit être un objet.")
    return obj


def _mistral_message_content_to_text(content) -> str:
    """Normalise message.content (str ou liste de fragments Mistral) en une seule chaîne."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, dict):
                if chunk.get("type") == "text" and chunk.get("text"):
                    parts.append(str(chunk["text"]))
                elif "text" in chunk:
                    parts.append(str(chunk["text"]))
                elif isinstance(chunk.get("content"), str):
                    parts.append(chunk["content"])
            elif isinstance(chunk, str):
                parts.append(chunk)
        return "".join(parts)
    return str(content)


async def generate_and_persist_theme_from_ai(context: str) -> Theme:
    """Appelle Mistral puis insère le thème, les sous-thèmes et les questions."""
    raw = await _generate_theme_ai(context)
    if isinstance(raw, str):
        raise HTTPException(status_code=502, detail=raw)
    return await _persist_generated_theme_from_ai(raw)


async def _generate_theme_ai(context: str):
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."

    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"

    prompt = """
        Génère un thème d'apprentissage original et structuré sur """ + context + """. Le thème doit comporter 8 à 10 piliers de savoir (domaines) couvrant les aspects techniques, théoriques, applicatifs, éthiques et historiques. Chaque domaine doit être formulé de manière à susciter la curiosité et à permettre une exploration approfondie et suivi d'environ 20 questions pour évaluer la connaissance de l'apprenant.
        Les résultats devront se présenter sous la forme d'un fichier JSON strict (aucun texte hors du JSON) au format suivant :
        {
            "titre" : ".....",
            "accroche" : "......",
            "description" : ".......",
            "domaines" :
                [
                    {
                    "titre" : "......",
                    "description" : ".......",
                    "questions" :
                        [
                            "Texte de la question 1",
                            "Texte de la question 2"
                        ]
                    }
                ]
        }
        Le titre du thème et de chaque domaine doit être concis et évocateur. L'accroche du thème est une phrase accrocheuse ; les descriptions font au plus 2 phrases. Les questions évaluent la compréhension des concepts du domaine. Utilise obligatoirement les clés "titre", "accroche", "description", "domaines", et dans chaque domaine "titre", "description", "questions" (tableau de chaînes).
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
                return f"Erreur : pas de contenu dans la réponse. Réponse : {str(data)[:800]}"

            response_json = _parse_json_object_from_llm_content(response_text)

            label = (response_json.get("titre") or response_json.get("label") or "").strip()
            tagline = (response_json.get("accroche") or response_json.get("tagline") or "").strip()
            description = (response_json.get("description") or "").strip()
            domaines = response_json.get("domaines") or []

            return {
                "label": label,
                "tagline": tagline,
                "description": description,
                "domaines": domaines,
            }

    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        return f"Erreur API Mistral (HTTP {e.response.status_code}) : {snippet}"
    except (ValueError, json.JSONDecodeError) as e:
        return f"Erreur : impossible d'extraire le JSON ({str(e)})."
    except httpx.TimeoutException:
        return "Erreur : timeout de la requête vers Mistral (délai dépassé)."
    except Exception as e:
        print("ERROR _generate_theme_ai:", repr(e))
        return f"Erreur : {str(e)}"


class GenerateThemeAiPersistPayload(PydanticBaseModel):
    content: str


class GenerateParcoursFromThemePayload(PydanticBaseModel):
    """Corps attendu par le front pour `generateParcoursAndQuestionsFromTheme` (api.service.ts)."""

    model_config = ConfigDict(populate_by_name=True)
    theme_id: int = Field(
        ...,
        validation_alias=AliasChoices("themeId", "idTheme", "id_theme"),
    )


@router.post("/generate-parcours-and-questions", response_model=Theme)
async def generate_parcours_and_questions_from_theme_endpoint(
    body: GenerateParcoursFromThemePayload,
):
    """
    Génère les parcours (sous-thèmes) et les questions via Mistral pour un thème existant,
    puis les enregistre avec la même logique que `_persist_domaines_under_theme`
    (facteur commun avec `_persist_generated_theme_from_ai`).
    """
    try:
        return await generate_parcours_and_questions_from_theme(body.theme_id)
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR generate_parcours_and_questions_from_theme_endpoint:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate_theme_ai/persist", response_model=Theme)
async def generate_theme_ai_persist(body: GenerateThemeAiPersistPayload):
    ctx = (body.content or "").strip()
    if not ctx:
        raise HTTPException(status_code=400, detail="Contexte vide.")
    try:
        return await generate_and_persist_theme_from_ai(ctx)
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR generate_theme_ai_persist:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route(
    "/generate_theme_ai/persist/{context:path}",
    methods=["GET", "POST"],
    response_model=Theme,
)
async def generate_theme_ai_persist_path(context: str):
    """Même effet que POST /generate_theme_ai/persist mais le sujet est dans l'URL (ex. …/persist/Machine%20Learning)."""
    ctx = (context or "").strip()
    if not ctx:
        raise HTTPException(status_code=400, detail="Contexte vide.")
    try:
        return await generate_and_persist_theme_from_ai(ctx)
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR generate_theme_ai_persist_path:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generate_theme_ai/{context:path}")
async def get_generate_theme_ai(context: str):
    return await _generate_theme_ai(context)
