import asyncio
import logging
import os
import httpx
from pathlib import Path
import shutil
from unittest import result
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
import whisper
import json
from io import StringIO
from openai import BaseModel
from pydantic import AliasChoices, BaseModel as PydanticBaseModel, ConfigDict, Field
from uuid import uuid4
import database

from queries import *
from fastapi.responses import FileResponse
from typing import List, Optional, Set, Tuple
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker
from mistralai.client import Mistral
from mistral.theme_mistral import generate_theme_ai as mistral_generate_theme_ai

router = APIRouter(prefix="/themes", tags=["themes"])
# Routes attendues par le front sans préfixe /themes (ex. PUT /subthemes/27)
subthemes_router = APIRouter(prefix="/subthemes", tags=["subthemes"])

DEFAULT_AI_QUESTION_TYPE = "ouverte"
# Regroupement IA : nombre de familles libre (homogénéité), plafonné côté API / prompt.
REGROUPEMENT_FAMILLES_MAX = 6

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
    id_discipline: int = Field(
        ...,
        validation_alias=AliasChoices("id_discipline", "idDiscipline"),
    )
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


class RegroupementQuestionsParcoursPayload(PydanticBaseModel):
    """Corps `POST /themes/regroupement_questions_parcours` (aligné sur api.service.ts)."""

    model_config = ConfigDict(populate_by_name=True)
    id_subtheme: str | int = Field(
        ...,
        validation_alias=AliasChoices("id_subtheme", "idSubtheme"),
    )


class RegroupementQuestionFamilleDto(PydanticBaseModel):
    libelle: str
    id_questions: List[int]


class RegroupementQuestionsParcoursResponse(PydanticBaseModel):
    familles: List[RegroupementQuestionFamilleDto]
    message: Optional[str] = None


def _ai_optional_text(raw) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _ai_string_list(raw) -> list:
    """Normalise un champ JSON liste (libellés)."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _ai_string_list_for_db(raw) -> Optional[str]:
    """
    Sérialise une liste pour PostgreSQL (colonnes TEXT ou JSONB).
    asyncpg attend une chaîne pour TEXT ; JSONB accepte aussi une chaîne JSON.
    """
    items = _ai_string_list(raw)
    if not items:
        return None
    return json.dumps(items, ensure_ascii=False)


def _question_libelle_from_ai_entry(entry) -> Optional[str]:
    if entry is None:
        return None
    if isinstance(entry, str):
        s = entry.strip()
        return s or None
    if isinstance(entry, dict):
        lib = entry.get("libelle") or entry.get("label")
        if isinstance(lib, str) and lib.strip():
            return lib.strip()
        for v in entry.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    s = str(entry).strip()
    return s or None


def _parse_ai_question_entry(entry) -> Optional[dict]:
    """Extrait libellé et métadonnées cognitives d'une question IA (objet ou chaîne legacy)."""
    if entry is None:
        return None
    if isinstance(entry, str):
        libelle = entry.strip()
        if not libelle:
            return None
        return {
            "libelle": libelle,
            "niveau_cognitif": None,
            "objectif_pedagogique": None,
            "concepts_vises": [],
        }
    if isinstance(entry, dict):
        libelle = _question_libelle_from_ai_entry(entry)
        if not libelle:
            return None
        return {
            "libelle": libelle,
            "niveau_cognitif": _ai_optional_text(entry.get("niveau_cognitif")),
            "objectif_pedagogique": _ai_optional_text(
                entry.get("objectif_pedagogique")
            ),
            "concepts_vises": _ai_string_list(entry.get("concepts_vises")),
        }
    return None


def _iter_domaine_questions(questions_raw):
    if questions_raw is None:
        return
    if isinstance(questions_raw, dict):
        for item in questions_raw.values():
            yield item
    elif isinstance(questions_raw, list):
        for item in questions_raw:
            yield item


async def _ensure_discipline_exists(id_discipline: int) -> None:
    rows = await postgres_select_query(
        "SELECT 1 FROM discipline WHERE id_discipline = $1 LIMIT 1",
        id_discipline,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Discipline introuvable")


async def _fetch_questions_libelles_for_subtheme(id_subtheme: int) -> List[dict]:
    """Charge tous les couples (id_question, libelle) pour un parcours (`id_subtheme`)."""
    rows = await postgres_select_query(
        """
        SELECT id_question, libelle
        FROM question
        WHERE id_subtheme = $1
        ORDER BY id_question
        """,
        id_subtheme,
    )
    return [
        {
            "id_question": int(r["id_question"]),
            "libelle": (r["libelle"] or "").strip(),
        }
        for r in rows
    ]


async def _ensure_subtheme_exists(id_subtheme: int) -> None:
    rows = await postgres_select_query(
        "SELECT 1 FROM subtheme WHERE id_subtheme = $1 LIMIT 1",
        id_subtheme,
    )
    if not rows:
        raise HTTPException(
            status_code=404, detail="Parcours (sous-thème) introuvable"
        )


def _parse_subtheme_id_from_payload(raw: str | int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="id_subtheme invalide.")
    if n < 1:
        raise HTTPException(status_code=400, detail="id_subtheme invalide.")
    return n


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
        await _ensure_discipline_exists(payload.id_discipline)
        theme_id = await postgres_insert_query(
            """
            INSERT INTO theme (label, tagline, description, id_discipline)
            VALUES ($1, $2, $3, $4)
            RETURNING id_theme
            """,
            payload.label,
            payload.tagline,
            payload.description,
            payload.id_discipline,
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
    except HTTPException:
        raise
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
            ORDER BY q.id_question
            """,
            subtheme_id,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regroupement_questions_parcours", response_model=RegroupementQuestionsParcoursResponse)
async def regroupement_questions_parcours(body: RegroupementQuestionsParcoursPayload,):
    """
    Regroupe les questions d'un parcours via Mistral puis enregistre `question.groupe` (1…n, n ≤ 6)
    et le libellé de famille JSON (`libelle` par famille) dans `question.libelle_groupe`.
    Le nombre de familles est choisi par le modèle selon l'homogénéité (plafond 6), sans paramètre client.
    Aligné sur `POST /themes/regroupement_questions_parcours` (api.service.ts).
    """
    id_subtheme = _parse_subtheme_id_from_payload(body.id_subtheme)

    try:
        await _ensure_subtheme_exists(id_subtheme)
        questions = await _fetch_questions_libelles_for_subtheme(id_subtheme)
        if not questions:
            raise HTTPException(
                status_code=400,
                detail="Aucune question pour ce parcours.",
            )

        expected_ids = {q["id_question"] for q in questions}
        used_fallback = False
        try:
            llm_obj = await _mistral_regroupe_questions_par_cours(questions)
            familles_dto, updates = _normalize_regroupement_familles_llm(
                llm_obj,
                expected_ids,
            )
        except HTTPException as exc:
            if exc.status_code != 502:
                raise
            logging.warning(
                "regroupement_questions_parcours: repli local après 502 — %s",
                exc.detail,
            )
            familles_dto, updates = _regroupement_partition_locale_sans_ia(questions)
            used_fallback = True

        await _apply_question_groupes_transaction(id_subtheme, updates)

        return RegroupementQuestionsParcoursResponse(
            familles=familles_dto,
            message=(
                "Regroupement enregistré en base (groupe, libelle_groupe)."
                + (
                    " Attention : repli local sans Mistral (réponse IA illisible, erreur API Mistral ou partition invalide)."
                    if used_fallback
                    else ""
                )
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("regroupement_questions_parcours")
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
        await _ensure_discipline_exists(payload.id_discipline)
        theme_id = await postgres_insert_query(
            """
            INSERT INTO theme (label, tagline, description, id_discipline)
            VALUES ($1, $2, $3, $4)
            RETURNING id_theme
            """,
            payload.label,
            payload.tagline,
            payload.description,
            payload.id_discipline,
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
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR create_theme:", e)
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_existing_domaines_for_theme(theme_id: int) -> List[dict]:
    """Parcours déjà en base pour un thème (contexte anti-redondance Mistral)."""
    rows = await postgres_select_query(
        """
        SELECT label, description, niveau_pyramide, role_cognitif
        FROM subtheme
        WHERE id_theme = $1
        ORDER BY id_subtheme
        """,
        theme_id,
    )
    return [dict(r) for r in rows]


async def _resolve_existing_domaines_for_theme(
    theme_id: int,
    from_client: Optional[List[dict]] = None,
) -> List[dict]:
    """Union par label : base de données + liste éventuelle envoyée par le client."""
    merged: dict[str, dict] = {}
    for row in await _fetch_existing_domaines_for_theme(theme_id):
        lab = (row.get("label") or "").strip()
        if lab:
            merged[lab.lower()] = row
    if from_client:
        for row in from_client:
            if not isinstance(row, dict):
                continue
            lab = (row.get("label") or row.get("titre") or "").strip()
            if not lab:
                continue
            merged[lab.lower()] = {
                "label": lab,
                "description": (row.get("description") or "").strip(),
                "niveau_pyramide": (row.get("niveau_pyramide") or "").strip() or None,
                "role_cognitif": (row.get("role_cognitif") or "").strip() or None,
            }
    return list(merged.values())


async def _persist_domaines_under_theme(
    theme_id: int,
    domaines: list,
    *,
    skip_labels: Optional[Set[str]] = None,
) -> int:
    """Crée parcours (sous-thèmes) et questions ; ignore les labels déjà présents. Retourne le nombre créé."""
    skip = skip_labels or set()
    created = 0
    for dom in domaines:
        if not isinstance(dom, dict):
            continue
        sub_lab = (dom.get("titre") or dom.get("label") or "").strip()
        sub_desc = (dom.get("description") or "").strip()
        if not sub_lab:
            continue
        if sub_lab.lower() in skip:
            continue
        sub_id = await postgres_insert_query(
            """
            INSERT INTO subtheme (
                id_theme,
                label,
                description,
                niveau_pyramide,
                role_cognitif,
                transformations_cognitives,
                prerequis,
                ouvre_vers
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id_subtheme
            """,
            theme_id,
            sub_lab,
            sub_desc,
            _ai_optional_text(dom.get("niveau_pyramide")),
            _ai_optional_text(dom.get("role_cognitif")),
            _ai_string_list_for_db(dom.get("transformations_cognitives")),
            _ai_string_list_for_db(dom.get("prerequis")),
            _ai_string_list_for_db(dom.get("ouvre_vers")),
        )
        for q in _iter_domaine_questions(dom.get("questions")):
            parsed = _parse_ai_question_entry(q)
            if not parsed:
                continue
            await postgres_insert_query(
                """
                INSERT INTO question (
                    libelle,
                    type,
                    id_subtheme,
                    niveau_cognitif,
                    objectif_pedagogique,
                    concepts_vises
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id_question
                """,
                parsed["libelle"],
                DEFAULT_AI_QUESTION_TYPE,
                sub_id,
                parsed["niveau_cognitif"],
                parsed["objectif_pedagogique"],
                _ai_string_list_for_db(parsed.get("concepts_vises")),
            )
        created += 1
    return created


async def _persist_generated_theme_from_ai(ai_payload: dict, id_discipline: int) -> Theme:
    """Enregistre en base un JSON de thème généré (label, tagline, description, domaines → subthemes + questions)."""
    await _ensure_discipline_exists(id_discipline)
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
        INSERT INTO theme (label, tagline, description, id_discipline)
        VALUES ($1, $2, $3, $4)
        RETURNING id_theme
        """,
        label,
        tagline,
        description,
        id_discipline,
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


async def generate_parcours_and_questions_from_theme(
    theme_id: int,
    existing_domaines: Optional[List[dict]] = None,
) -> Theme:
    """
    À partir d’un thème déjà en base (ex. squelette issu d’une discipline),
    appelle l’IA puis enregistre domaines → sous-thèmes + questions sur ce même id_theme.
    existing_domaines : parcours déjà générés (fusionnés avec subtheme en base).
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

    existing = await _resolve_existing_domaines_for_theme(
        theme_id, existing_domaines
    )

    raw = await _generate_theme_ai(context, existing_domaines=existing)
    if isinstance(raw, str):
        raise HTTPException(status_code=502, detail=raw)

    domaines = raw.get("domaines") or []
    if raw.get("partial"):
        logging.warning(
            "generate_parcours_and_questions: JSON Mistral tronqué — %s domaine(s) "
            "complets enregistrés pour theme_id=%s",
            len(domaines),
            theme_id,
        )
    skip_labels = {
        (d.get("label") or d.get("titre") or "").strip().lower()
        for d in existing
        if (d.get("label") or d.get("titre") or "").strip()
    }
    created = await _persist_domaines_under_theme(
        theme_id, domaines, skip_labels=skip_labels
    )
    if created == 0 and domaines:
        logging.warning(
            "generate_parcours_and_questions: %s domaine(s) IA ignoré(s) (doublons de label) "
            "pour theme_id=%s",
            len(domaines),
            theme_id,
        )
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


def _parse_regroupement_llm_response_text(content: str) -> dict:
    """
    Parse la réponse Mistral pour le regroupement : accepte un objet {\"familles\":...}
    ou un tableau [...] de familles (le modèle renvoie parfois uniquement le tableau).
    """
    text = _strip_markdown_json_fence((content or "").strip())
    if not text:
        raise ValueError("Réponse vide.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        t2 = text.strip()
        if t2.startswith("["):
            try:
                parsed = json.loads(t2)
            except json.JSONDecodeError:
                return _parse_json_object_from_llm_content(content)
        else:
            return _parse_json_object_from_llm_content(content)

    if isinstance(parsed, list):
        if not parsed:
            raise ValueError("Tableau JSON vide.")
        first = parsed[0]
        if isinstance(first, dict) and any(
            k in first
            for k in (
                "id_questions",
                "idQuestions",
                "libelle",
                "label",
                "ids",
                "id_question",
                "question_ids",
            )
        ):
            return {"familles": parsed}
        raise ValueError(
            "JSON tableau non reconnu : attendu une liste d'objets famille "
            "(libelle, id_questions)."
        )

    if isinstance(parsed, dict):
        return parsed

    raise ValueError("JSON racine doit être un objet ou un tableau.")


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


def _coerce_question_id_llm(value) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, float):
            if not value.is_integer():
                return None
            return int(value)
        return int(value)
    except (TypeError, ValueError):
        return None


_FAMILLES_JSON_KEYS = frozenset(
    (
        "familles",
        "groupes",
        "groups",
        "clusters",
        "categories",
        "families",
    )
)


def _get_familles_raw_from_dict(container: dict):
    """Liste / objet des familles sous plusieurs noms de clés (FR/EN, casse)."""
    for key in _FAMILLES_JSON_KEYS:
        if key in container:
            return container[key]
    for k, v in container.items():
        if isinstance(k, str) and k.lower() in _FAMILLES_JSON_KEYS:
            return v
    return None


def _unwrap_regroupement_llm_root(obj: dict) -> dict:
    """Normalise vers {\"familles\": [...]} ; accepte enveloppes et clés de casse variables."""
    if not isinstance(obj, dict):
        raise HTTPException(
            status_code=502,
            detail="Réponse IA : racine JSON invalide (objet attendu).",
        )

    raw = _get_familles_raw_from_dict(obj)
    if isinstance(raw, str) and raw.strip().startswith("["):
        try:
            inner = json.loads(raw.strip())
            if isinstance(inner, list):
                return {"familles": inner}
        except json.JSONDecodeError:
            pass
    if isinstance(raw, (list, dict)):
        return {"familles": raw}

    for wrap_key in ("result", "data", "output", "response", "reponse", "answer"):
        inner = obj.get(wrap_key)
        if isinstance(inner, dict):
            raw = _get_familles_raw_from_dict(inner)
            if isinstance(raw, str) and raw.strip().startswith("["):
                try:
                    inner_list = json.loads(raw.strip())
                    if isinstance(inner_list, list):
                        return {"familles": inner_list}
                except json.JSONDecodeError:
                    pass
            if isinstance(raw, (list, dict)):
                return {"familles": raw}
        if isinstance(inner, list) and inner and isinstance(inner[0], dict):
            if any(
                x in inner[0]
                for x in ("id_questions", "libelle", "label", "idQuestions", "ids")
            ):
                return {"familles": inner}

    for v in obj.values():
        if isinstance(v, str) and v.strip().startswith("["):
            try:
                inner_list = json.loads(v.strip())
                if (
                    isinstance(inner_list, list)
                    and inner_list
                    and isinstance(inner_list[0], dict)
                ):
                    if any(
                        x in inner_list[0]
                        for x in (
                            "id_questions",
                            "libelle",
                            "label",
                            "idQuestions",
                        )
                    ):
                        return {"familles": inner_list}
            except json.JSONDecodeError:
                continue

    if len(obj) == 1:
        v = next(iter(obj.values()))
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if any(
                x in v[0]
                for x in ("id_questions", "libelle", "label", "idQuestions")
            ):
                return {"familles": v}

    raise HTTPException(
        status_code=502,
        detail='Réponse IA : clé "familles" (ou équivalent) introuvable ou structure inconnue.',
    )


def _familles_raw_to_list(raw) -> List:
    """Tableau JSON ou objet { \"0\": {...}, \"1\": {...} }."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        keys = sorted(
            raw.keys(),
            key=lambda x: (0, int(x)) if str(x).isdigit() else (1, str(x)),
        )
        return [raw[k] for k in keys]
    raise HTTPException(
        status_code=502,
        detail='Réponse IA : "familles" doit être un tableau ou un objet.',
    )


_FAMILY_TITLE_KEYS = (
    "libelle_groupe",
    "libelle_famille",
    "titre_famille",
    "nom_famille",
    "libelle",
    "label",
)


def _item_a_liste_id_questions(item: dict) -> bool:
    """True si l’entrée décrit une famille (liste d’ids), pas une ligne question isolée."""
    return any(
        item.get(k) is not None
        for k in ("id_questions", "idQuestions", "questions_ids", "question_ids", "ids")
    )


def _libelle_titre_famille_depuis_item(item: dict) -> str:
    """
    Titre de famille à persister dans `libelle_groupe`.
    Quand Mistral fournit `id_questions`, on n’utilise pas les clés génériques `titre` / `nom` / `title` :
    le modèle y met souvent le libellé d’une question, ce qui écrase le vrai titre de groupe.
    """
    if _item_a_liste_id_questions(item):
        for k in _FAMILY_TITLE_KEYS:
            v = item.get(k)
            if v is None:
                continue
            s = _regroupement_famille_libelle_to_str(v)
            if s:
                return s
        return ""
    for k in _FAMILY_TITLE_KEYS + ("titre", "nom", "title"):
        v = item.get(k)
        if v is None:
            continue
        s = _regroupement_famille_libelle_to_str(v)
        if s:
            return s
    return ""


def _regroupement_famille_libelle_to_str(raw) -> str:
    """Normalise le libellé de **famille** Mistral (pas un libellé de question au hasard)."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return str(raw).strip()
    if isinstance(raw, dict):
        for k in _FAMILY_TITLE_KEYS:
            if k not in raw:
                continue
            inner = raw[k]
            if isinstance(inner, dict):
                for loc in ("fr", "en", "default"):
                    if loc in inner and isinstance(inner[loc], str) and inner[loc].strip():
                        return inner[loc].strip()
                s = _regroupement_famille_libelle_to_str(inner)
                if s:
                    return s
            else:
                s = _regroupement_famille_libelle_to_str(inner)
                if s:
                    return s
        return ""
    return str(raw).strip()


def _coerce_id_questions_raw_to_list(ids_raw):
    """Liste d'id ou id unique (nombre ou chaîne numérique)."""
    if ids_raw is None:
        return None
    if isinstance(ids_raw, list):
        return ids_raw
    if isinstance(ids_raw, (int, float)) and not isinstance(ids_raw, bool):
        return [ids_raw]
    if isinstance(ids_raw, str):
        s = ids_raw.strip()
        if s.isdigit():
            return [int(s)]
        if "," in s or ";" in s:
            out: List[int] = []
            for part in s.replace(";", ",").split(","):
                p = part.strip()
                if not p:
                    continue
                cid = _coerce_question_id_llm(p)
                if cid is not None:
                    out.append(cid)
            return out if out else None
        return None
    return None


def _merge_familles_jusqua_max(
    familles: List[dict],
    max_familles: int,
    expected_ids: Set[int],
) -> Optional[List[dict]]:
    """
    Fusionne des familles depuis la fin jusqu'à ≤ max_familles,
    si les id_questions forment déjà une partition de expected_ids (sans doublon).
    """
    flat: List[int] = []
    for f in familles:
        flat.extend(f["id_questions"])
    if len(flat) != len(expected_ids) or set(flat) != expected_ids:
        return None
    if len(set(flat)) != len(flat):
        return None

    items: List[dict] = [dict(f) for f in familles]

    while len(items) > max_familles:
        b = items.pop()
        a = items.pop()
        items.append(
            {
                "libelle": f"{a['libelle']} — {b['libelle']}",
                "id_questions": a["id_questions"] + b["id_questions"],
            }
        )

    return items


def _regroupement_partition_locale_sans_ia(
    questions: List[dict],
) -> Tuple[List[RegroupementQuestionFamilleDto], List[Tuple[int, int, str]]]:
    """
    Répartition déterministe (round-robin sur id_question) si Mistral ou le JSON échoue.
    Garantit un regroupement en base sans HTTP 502 bloquant.
    Utilise au plus REGROUPEMENT_FAMILLES_MAX groupes (jamais plus de seaux que de questions).
    """
    sorted_q = sorted(questions, key=lambda q: int(q["id_question"]))
    n_buckets = min(REGROUPEMENT_FAMILLES_MAX, len(sorted_q))
    n_buckets = max(1, n_buckets)
    buckets: List[List[int]] = [[] for _ in range(n_buckets)]
    for i, q in enumerate(sorted_q):
        buckets[i % n_buckets].append(int(q["id_question"]))

    dto_list: List[RegroupementQuestionFamilleDto] = []
    updates: List[Tuple[int, int, str]] = []

    for idx, gids in enumerate(buckets):
        groupe_idx = idx + 1
        # Ne pas reprendre le libellé des questions : ce n’est pas le titre de famille Mistral.
        libelle = f"Famille {groupe_idx} (regroupement automatique)"

        dto_list.append(
            RegroupementQuestionFamilleDto(libelle=libelle, id_questions=list(gids))
        )
        for qid in gids:
            updates.append((qid, groupe_idx, libelle))

    return dto_list, updates


def _normalize_regroupement_familles_llm(
    obj: dict,
    expected_ids: Set[int],
) -> Tuple[
    List[RegroupementQuestionFamilleDto],
    List[Tuple[int, int, str]],
]:
    """
    Valide le JSON Mistral et renvoie les DTO + affectations
    (id_question, groupe, libelle_groupe) avec groupe dans 1 … n (n ≤ REGROUPEMENT_FAMILLES_MAX).
    """
    root = _unwrap_regroupement_llm_root(obj)
    raw_familles = _familles_raw_to_list(root.get("familles"))

    preliminary: List[dict] = []
    seen: Set[int] = set()

    for item in raw_familles:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=502,
                detail="Entrée de famille invalide dans la réponse IA.",
            )
        libelle = _libelle_titre_famille_depuis_item(item)

        # Ne pas utiliser id_question (singulier) : Mistral renvoie parfois des lignes « question »
        # { id_question, libelle } ; les prendre pour des familles recopie le libellé question dans libelle_groupe.
        ids_raw = (
            item.get("id_questions")
            or item.get("idQuestions")
            or item.get("questions_ids")
            or item.get("question_ids")
            or item.get("ids")
        )
        ids_raw = _coerce_id_questions_raw_to_list(ids_raw)
        if ids_raw is None:
            raise HTTPException(
                status_code=502,
                detail='Champ "id_questions" manquant ou invalide pour une famille.',
            )

        ids_int: List[int] = []
        for x in ids_raw:
            cid = _coerce_question_id_llm(x)
            if cid is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"id_question invalide dans une famille : {x!r}",
                )
            if cid not in expected_ids:
                raise HTTPException(
                    status_code=502,
                    detail=f"id_question {cid} inconnu pour ce parcours.",
                )
            # Mistral peut dupliquer un id dans plusieurs familles : on garde la première
            # affectation (ordre du JSON) pour que libelle_groupe en base = libelle JSON.
            if cid in seen:
                logging.warning(
                    "regroupement: id_question %s ignoré en doublon (famille « %s ») ; "
                    "conservé dans une famille précédente.",
                    cid,
                    libelle[:80] if libelle else "?",
                )
                continue
            seen.add(cid)
            ids_int.append(cid)

        if not ids_int:
            logging.warning(
                'regroupement: famille sans id_questions exploitable après dédoublonnage (libelle="%s")',
                libelle[:120] if libelle else "",
            )
            continue

        if not libelle:
            libelle = f"Famille {len(preliminary) + 1}"

        preliminary.append({"libelle": libelle, "id_questions": ids_int})

    if seen != expected_ids:
        missing = sorted(expected_ids - seen)
        raise HTTPException(
            status_code=502,
            detail=(
                "La répartition ne couvre pas exactement l'ensemble des questions du parcours."
                + (f" Manquantes : {missing}." if missing else "")
            ),
        )

    if not preliminary:
        raise HTTPException(
            status_code=502,
            detail="Aucune famille exploitable dans la réponse IA.",
        )

    if len(preliminary) > REGROUPEMENT_FAMILLES_MAX:
        merged = _merge_familles_jusqua_max(
            preliminary, REGROUPEMENT_FAMILLES_MAX, expected_ids
        )
        if merged is None:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"L'IA a produit trop de familles ({len(preliminary)}). La fusion automatique "
                    f"jusqu'à {REGROUPEMENT_FAMILLES_MAX} maximum a échoué."
                ),
            )
        preliminary = merged

    dto_list: List[RegroupementQuestionFamilleDto] = []
    updates: List[Tuple[int, int, str]] = []

    for idx, fam in enumerate(preliminary):
        groupe_idx = idx + 1
        libelle_famille = str(fam.get("libelle") or "").strip()
        if not libelle_famille:
            libelle_famille = f"Famille {groupe_idx}"
        dto_list.append(
            RegroupementQuestionFamilleDto(
                libelle=libelle_famille,
                id_questions=fam["id_questions"],
            )
        )
        for qid in fam["id_questions"]:
            updates.append((qid, groupe_idx, libelle_famille))

    return dto_list, updates


async def _mistral_regroupe_questions_par_cours(
    questions: List[dict],
) -> dict:
    """Envoie les questions à Mistral et retourne l'objet JSON parsé."""
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Variable d'environnement MISTRAL_API_KEY manquante ou vide.",
        )

    questions_json = json.dumps(questions, ensure_ascii=False)
    max_f = REGROUPEMENT_FAMILLES_MAX
    prompt = (
        "Tu es un expert en pédagogie et en analyse de contenus.\n\n"
        "Voici les questions d'un même parcours d'apprentissage (JSON : id_question, libelle) :\n"
        f"{questions_json}\n\n"
        "Regroupe ces questions en familles homogènes (thème ou type de compétence), en t'appuyant "
        "uniquement sur les libellés des questions. Le NOMBRE de familles n'est pas fixé à l'avance : "
        "choisis-le selon l'homogénéité naturelle des contenus (évite de fusionner des thèmes trop "
        f"différents ; évite aussi d'éclater artificiellement). Limite stricte : au plus {max_f} "
        "familles au total (jamais plus).\n"
        "Chaque question doit apparaître dans une et une seule famille : chaque id_question "
        "exactement une fois dans tout le JSON (aucun doublon entre familles). Utilise exactement les "
        "id_question fournis (entiers) ; n'en invente pas.\n\n"
        "Pour CHAQUE famille, tu dois fournir :\n"
        '- "libelle" : un titre court et explicite en français (3 à 12 mots) qui résume le thème '
        "commun des questions de cette famille ; ce libellé sera stocké en base pour chaque "
        "question du groupe.\n"
        '- "id_questions" : tableau d\'entiers — toujours un tableau JSON (ex. [42] pour une seule '
        "question). N'utilise pas la clé \"id_question\" au niveau famille : uniquement "
        "\"id_questions\" pour lister les questions du groupe.\n\n"
        "Réponds uniquement par un objet JSON de ce format exact (aucun texte hors JSON) :\n"
        '{"familles":[\n'
        '  {"libelle":"Exemple de titre de famille","id_questions":[1,2,3]},\n'
        '  ...\n'
        "]}\n"
        f'La clé racine obligatoire est "familles". Elle contient entre 1 et {max_f} objets '
        '(inclus). Chaque objet a obligatoirement les deux clés "libelle" et "id_questions".'
    )

    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            payloads = (
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            last_parse_msg: Optional[str] = None
            for req_payload in payloads:
                response = await client.post(url, headers=headers, json=req_payload)
                if response.status_code == 400 and req_payload.get("response_format"):
                    req_payload = {
                        k: v for k, v in req_payload.items()
                        if k != "response_format"
                    }
                    response = await client.post(url, headers=headers, json=req_payload)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise HTTPException(
                        status_code=502,
                        detail="Réponse Mistral sans choices.",
                    )
                message = (choices[0] or {}).get("message") or {}
                response_text = _mistral_message_content_to_text(message.get("content"))

                if not response_text.strip():
                    raise HTTPException(status_code=502, detail="Réponse Mistral vide.")
                try:
                    return _parse_regroupement_llm_response_text(response_text)
                except ValueError as e:
                    last_parse_msg = str(e)
                    continue
            raise HTTPException(
                status_code=502,
                detail=(
                    "Réponse IA illisible ou structure inattendue après 2 appels Mistral."
                    + (f" Dernier essai : {last_parse_msg}" if last_parse_msg else "")
                ),
            )
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        raise HTTPException(
            status_code=502,
            detail=f"Erreur API Mistral (HTTP {e.response.status_code}) : {snippet}",
        ) from e
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=502,
            detail="Timeout de la requête vers Mistral.",
        ) from None


async def _apply_question_groupes_transaction(
    id_subtheme: int,
    updates: List[Tuple[int, int, str]],
) -> None:
    """Met à jour `question.groupe` (1…n) et `question.libelle_groupe` dans une transaction."""
    if database.pool is None:
        raise HTTPException(
            status_code=500,
            detail="Pool base de données non initialisé.",
        )
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            # Même si init_db n’a pas été rejoué après ajout du code.
            await conn.execute(
                "ALTER TABLE question ADD COLUMN IF NOT EXISTS libelle_groupe TEXT"
            )
            missing: List[int] = []
            for id_question, groupe, libelle_groupe in updates:
                # Cast explicites côté SQL : évite les refus asyncpg selon le type PG réel.
                groupe_db = str(groupe).strip()
                lib_db = (
                    str(libelle_groupe).strip()
                    if libelle_groupe is not None
                    else ""
                )
                row = await conn.fetchrow(
                    """
                    UPDATE question
                    SET groupe = $1::text,
                        libelle_groupe = $2::text
                    WHERE id_question = $3::int
                      AND id_subtheme = $4::int
                    RETURNING id_question, libelle_groupe
                    """,
                    groupe_db,
                    lib_db,
                    id_question,
                    id_subtheme,
                )
                if row is None:
                    missing.append(id_question)
            if missing:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Aucune ligne mise à jour pour certaines questions "
                        f"(id_subtheme={id_subtheme}, ids={missing[:30]}…). "
                        "Vérifiez que id_question et id_subtheme correspondent bien à la table question."
                    ),
                )


async def generate_and_persist_theme_from_ai(context: str, id_discipline: int) -> Theme:
    """Appelle Mistral puis insère le thème, les sous-thèmes et les questions."""
    raw = await _generate_theme_ai(context)
    if isinstance(raw, str):
        raise HTTPException(status_code=502, detail=raw)
    if not (raw.get("label") or "").strip():
        fallback = (context or "").strip().split(".")[0][:200].strip()
        raw = {**raw, "label": fallback or "Thème généré"}
    return await _persist_generated_theme_from_ai(raw, id_discipline)


async def _generate_theme_ai(
    context: str,
    existing_domaines: Optional[List[dict]] = None,
):
    """Délègue à mistral.theme_mistral (prompt domaines + questions enrichis)."""
    return await mistral_generate_theme_ai(
        context, existing_domaines=existing_domaines
    )


class GenerateThemeAiPersistPayload(PydanticBaseModel):
    model_config = ConfigDict(populate_by_name=True)
    content: str
    id_discipline: int = Field(
        ...,
        validation_alias=AliasChoices("id_discipline", "idDiscipline"),
    )


class ExistingDomaineSummary(PydanticBaseModel):
    """Parcours (domaine) déjà présent — envoyé au prompt pour éviter les redondances."""

    model_config = ConfigDict(populate_by_name=True)
    label: str
    description: str = ""
    niveau_pyramide: Optional[str] = None
    role_cognitif: Optional[str] = None


class GenerateParcoursFromThemePayload(PydanticBaseModel):
    """Corps attendu par le front pour `generateParcoursAndQuestionsFromTheme` (api.service.ts)."""

    model_config = ConfigDict(populate_by_name=True)
    theme_id: int = Field(
        ...,
        validation_alias=AliasChoices("themeId", "idTheme", "id_theme"),
    )
    existing_domaines: Optional[List[ExistingDomaineSummary]] = Field(
        default=None,
        validation_alias=AliasChoices(
            "existing_domaines",
            "existingDomaines",
            "domaines_existants",
            "domainesExistants",
        ),
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
        existing = None
        if body.existing_domaines is not None:
            existing = [d.model_dump() for d in body.existing_domaines]
        return await generate_parcours_and_questions_from_theme(
            body.theme_id,
            existing_domaines=existing,
        )
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
        return await generate_and_persist_theme_from_ai(ctx, body.id_discipline)
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
async def generate_theme_ai_persist_path(
    context: str,
    id_discipline: Optional[int] = Query(None),
    idDiscipline: Optional[int] = Query(None),
):
    """Même effet que POST /generate_theme_ai/persist mais le sujet est dans l'URL (ex. …/persist/Machine%20Learning)."""
    discipline_id = (
        id_discipline if id_discipline is not None else idDiscipline
    )
    if discipline_id is None:
        raise HTTPException(
            status_code=422,
            detail="Paramètre requis : id_discipline ou idDiscipline (query).",
        )
    ctx = (context or "").strip()
    if not ctx:
        raise HTTPException(status_code=400, detail="Contexte vide.")
    try:
        return await generate_and_persist_theme_from_ai(ctx, discipline_id)
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR generate_theme_ai_persist_path:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generate_theme_ai/{context:path}")
async def get_generate_theme_ai(context: str):
    return await _generate_theme_ai(context)

