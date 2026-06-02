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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, List, Literal, Optional
from datetime import date, datetime

import database
from queries import postgres_select_query
from mistral.discipline_mistral import (
    generate_list_themes_ai as _generate_list_themes_ai_mistral,
    propose_discipline_from_wish_ai as _propose_discipline_from_wish_ai_mistral,
)

router = APIRouter(prefix="/disciplines", tags=["disciplines"])

NiveauEstime = Literal["debutant", "intermediaire", "avance"]


class Discipline(BaseModel):
    id_discipline: int
    label: str
    description: Optional[str] = None
    niveau_estime: Optional[NiveauEstime] = None
    projection: Optional[str] = None


class DisciplineThemeSummary(BaseModel):
    id_theme: int
    label: str
    tagline: Optional[str] = None
    description: Optional[str] = None
    role_cognitif: Optional[str] = None
    niveau_pyramide: Optional[str] = None
    transformation_cognitive: Optional[str] = None


class DisciplineLinkedLabel(BaseModel):
    id: int
    label: str


class DisciplineDetail(Discipline):
    themes: List[DisciplineThemeSummary] = Field(default_factory=list)
    competences: List[DisciplineLinkedLabel] = Field(default_factory=list)
    prerequis: List[DisciplineLinkedLabel] = Field(default_factory=list)


class CreateDisciplinePayload(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    competences: List[str] = Field(default_factory=list)
    prerequis: List[str] = Field(default_factory=list)
    niveau_estime: NiveauEstime | None = None
    projection: str | None = None


class ProposeDisciplineFromWishPayload(BaseModel):
    """Souhait exprimé par l'utilisateur (formulation libre, souvent approximative)."""
    wish: str = Field(..., min_length=3, max_length=4000)


class ProposeDisciplineFromWishResult(BaseModel):
    label: str = Field(..., description="Intitulé court de la discipline proposée")
    description: str = Field(..., description="Description pédagogique proposée")
    competences: List[str] = Field(default_factory=list)
    prerequis: List[str] = Field(default_factory=list)
    niveau_estime: NiveauEstime | None = None
    projection: str | None = None


class UpdateDisciplinePayload(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    niveau_estime: NiveauEstime | None = None
    projection: str | None = None


# Fait: normalise une valeur de niveau estimé vers le vocabulaire interne.
# Entrées: `raw` (Any).
# Retour: `str | None`.
def _normalize_niveau_estime(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    v = raw.strip().lower().replace("é", "e").replace("è", "e")
    aliases = {
        "debutant": "debutant",
        "beginner": "debutant",
        "intermediaire": "intermediaire",
        "intermediate": "intermediaire",
        "avance": "avance",
        "advanced": "avance",
    }
    return aliases.get(v)


# Fait: nettoie/déduplique une liste de libellés.
# Entrées: `raw` (Any), `max_items` (int), `max_len` (int).
# Retour: `list[str]`.
def _normalize_label_list(raw: Any, *, max_items: int = 30, max_len: int = 500) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            lbl = item.strip()
        elif isinstance(item, dict):
            lbl = (item.get("label") or item.get("libelle") or "").strip()
        else:
            continue
        if not lbl:
            continue
        key = lbl.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(lbl[:max_len])
        if len(out) >= max_items:
            break
    return out


# Fait: insère des compétences ou prérequis pour une discipline.
# Entrées: `conn`, `discipline_id` (int), `labels` (list[str]), `entity` (Literal).
# Retour: `None`.
async def _insert_labels_for_discipline(
    conn,
    *,
    discipline_id: int,
    labels: list[str],
    entity: Literal["competence", "prerequis"],
) -> None:
    table = "competence" if entity == "competence" else "prerequis"
    for label in labels:
        await conn.execute(
            f"""
            INSERT INTO {table} (label, id_discipline)
            VALUES ($1, $2)
            """,
            label,
            discipline_id,
        )


# Fait: convertit une ligne SQL en modèle `Discipline`.
# Entrées: `row` (dict).
# Retour: `Discipline`.
def _discipline_from_row(row: dict) -> Discipline:
    niveau = row.get("niveau_estime")
    if niveau is not None and niveau not in ("debutant", "intermediaire", "avance"):
        niveau = None
    return Discipline(
        id_discipline=row["id_discipline"],
        label=row["label"],
        description=row.get("description"),
        niveau_estime=niveau,
        projection=row.get("projection"),
    )


@router.get("/all_disciplines", response_model=List[Discipline])
# Fait: retourne la liste des disciplines.
# Entrées: aucune.
# Retour: `List[Discipline]`.
async def get_all_disciplines():
    """
    Retourne la liste des disciplines triée par id pour avoir un ordre déterministe.
    Le front s'en sert pour afficher la popup de sélection.
    """
    try:
        rows = await postgres_select_query(
            """
            SELECT id_discipline, label, description, niveau_estime, projection
            FROM discipline
            ORDER BY id_discipline
            """
        )
        return [_discipline_from_row(row) for row in rows]
    except Exception as e:
        print("ERROR get_all_disciplines:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/propose_from_wish", response_model=ProposeDisciplineFromWishResult)
# Fait: propose une discipline à partir d'un souhait utilisateur.
# Entrées: `payload` (`ProposeDisciplineFromWishPayload`).
# Retour: `ProposeDisciplineFromWishResult`.
async def propose_discipline_from_wish(payload: ProposeDisciplineFromWishPayload):
    """
    À partir du souhait utilisateur, propose un intitulé et une description via Mistral.
    L'utilisateur valide ou modifie ces propositions avant `create_discipline`.
    """
    wish = payload.wish.strip()
    result = await _propose_discipline_from_wish_ai(wish)
    if isinstance(result, str):
        raise HTTPException(status_code=502, detail=result)
    return ProposeDisciplineFromWishResult(**result)


@router.post("/create_discipline")
# Fait: crée une discipline et ses thèmes/labels associés.
# Entrées: `payload` (`CreateDisciplinePayload`).
# Retour: `dict` représentant la discipline créée.
async def create_discipline(payload: CreateDisciplinePayload):
    label = payload.label.strip()
    description = (payload.description or "").strip() or None
    projection = (payload.projection or "").strip() or None
    niveau = payload.niveau_estime
    competences = _normalize_label_list(payload.competences)
    prerequis = _normalize_label_list(payload.prerequis)
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
                INSERT INTO discipline (label, description, niveau_estime, projection)
                VALUES ($1, $2, $3, $4)
                RETURNING id_discipline
                """,
                label,
                description,
                niveau,
                projection,
            )
            await _insert_labels_for_discipline(
                conn,
                discipline_id=new_id,
                labels=competences,
                entity="competence",
            )
            await _insert_labels_for_discipline(
                conn,
                discipline_id=new_id,
                labels=prerequis,
                entity="prerequis",
            )
            for item in themes_data:
                theme_id = await conn.fetchval(
                    """
                    INSERT INTO theme (
                        label,
                        tagline,
                        description,
                        role_cognitif,
                        niveau_pyramide,
                        transformation_cognitive,
                        id_discipline
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id_theme
                    """,
                    item["label"],
                    item.get("tagline") or "",
                    item.get("description") or "",
                    item.get("role_cognitif") or "",
                    item.get("niveau_pyramide") or "",
                    item.get("transformation_cognitive") or "",
                    new_id,
                )
                created_themes.append(
                    {
                        "id_theme": theme_id,
                        "label": item["label"],
                        "tagline": item.get("tagline") or "",
                        "description": item.get("description") or "",
                        "role_cognitif": item.get("role_cognitif") or "",
                        "niveau_pyramide": item.get("niveau_pyramide") or "",
                        "transformation_cognitive": item.get("transformation_cognitive") or "",
                    }
                )

    return {
        "id_discipline": new_id,
        "label": label,
        "description": description,
        "niveau_estime": niveau,
        "projection": projection,
        "themes": created_themes,
    }

# Fait: appelle Mistral pour proposer une discipline depuis un souhait.
# Entrées: `wish` (str).
# Retour: `dict | str` (résultat ou message d'erreur).
async def _propose_discipline_from_wish_ai(wish: str) -> dict | str:
    raw = await _propose_discipline_from_wish_ai_mistral(wish)
    if isinstance(raw, str):
        return raw
    label = (raw.get("label") or "").strip()
    description = (raw.get("description") or "").strip()
    if not label:
        return "Erreur : intitulé (label) vide ou absent dans la réponse JSON."
    if not description:
        return "Erreur : description vide ou absente dans la réponse JSON."
    competences = _normalize_label_list(raw.get("competences"))
    prerequis = _normalize_label_list(raw.get("prerequis"))
    niveau = _normalize_niveau_estime(raw.get("niveau_estime"))
    projection = (raw.get("projection") or "").strip() or None
    return {
        "label": label[:200],
        "description": description[:4000],
        "competences": competences,
        "prerequis": prerequis,
        "niveau_estime": niveau,
        "projection": (projection[:4000] if projection else None),
    }


# Fait: génère la liste de thèmes d'une discipline via Mistral.
# Entrées: `discipline_label` (str), `discipline_description` (str).
# Retour: `list[dict] | str` (liste de thèmes ou erreur).
async def _generate_list_themes_ai(discipline_label: str, discipline_description: str):
    raw = await _generate_list_themes_ai_mistral(discipline_label, discipline_description)
    if isinstance(raw, str):
        return raw
    themes_out = []
    for item in raw:
        label = (item.get("label") or "").strip()
        tagline = (item.get("tagline") or "").strip()
        description = (item.get("description") or "").strip()
        role_cognitif = (item.get("role_cognitif") or "").strip()
        niveau_pyramide = (item.get("niveau_pyramide") or "").strip()
        transformation_cognitive = (item.get("transformation_cognitive") or "").strip()
        if label:
            themes_out.append(
                {
                    "label": label,
                    "tagline": tagline,
                    "description": description or "",
                    "role_cognitif": role_cognitif,
                    "niveau_pyramide": niveau_pyramide,
                    "transformation_cognitive": transformation_cognitive,
                }
            )
    if not themes_out:
        return "Erreur : aucun thème exploitable (labels vides ou structure invalide)."
    return themes_out


class KnowledgeOverviewProposition(BaseModel):
    id_proposition: int
    date_creation: Optional[str] = None


class KnowledgeOverviewEvaluation(BaseModel):
    id_evaluation: int
    date_creation: Optional[str] = None


def _format_date_creation(value: Any) -> Optional[str]:
    """Normalise date_creation (datetime PostgreSQL ou TEXT) en chaîne ISO."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


class KnowledgeOverviewQuestion(BaseModel):
    id_question: int
    label: str
    propositions: List[KnowledgeOverviewProposition] = Field(default_factory=list)
    evaluations: List[KnowledgeOverviewEvaluation] = Field(default_factory=list)


class KnowledgeOverviewSubTheme(BaseModel):
    id_subtheme: int
    label: str
    questions: List[KnowledgeOverviewQuestion] = Field(default_factory=list)


class KnowledgeOverviewTheme(BaseModel):
    id_theme: int
    label: str
    subthemes: List[KnowledgeOverviewSubTheme] = Field(default_factory=list)


class KnowledgeOverviewDiscipline(BaseModel):
    id_discipline: int
    label: str
    themes: List[KnowledgeOverviewTheme] = Field(default_factory=list)


@router.get("/knowledge_overview", response_model=List[KnowledgeOverviewDiscipline])
async def get_knowledge_overview():
    """
    Arborescence complète discipline → thème → parcours → question → propositions / évaluations.
    Pour propositions et évaluations, seul `date_creation` est exposé pour l'instant.
    """
    try:
        discipline_rows = await postgres_select_query(
            """
            SELECT id_discipline, label
            FROM discipline
            ORDER BY id_discipline
            """
        )
        theme_rows = await postgres_select_query(
            """
            SELECT id_theme, label, id_discipline
            FROM theme
            ORDER BY id_discipline NULLS LAST, id_theme
            """
        )
        subtheme_rows = await postgres_select_query(
            """
            SELECT id_subtheme, id_theme, label
            FROM subtheme
            ORDER BY id_theme, id_subtheme
            """
        )
        question_rows = await postgres_select_query(
            """
            SELECT id_question, id_subtheme, libelle
            FROM question
            ORDER BY id_subtheme, id_question
            """
        )
        proposition_rows = await postgres_select_query(
            """
            SELECT id_proposition, id_question, date_creation
            FROM proposition
            ORDER BY id_question, id_proposition DESC
            """
        )
        evaluation_rows = await postgres_select_query(
            """
            SELECT id_evaluation, id_question, date_creation
            FROM evaluation
            ORDER BY id_question, id_evaluation DESC
            """
        )
    except Exception as e:
        print("ERROR get_knowledge_overview:", e)
        raise HTTPException(status_code=500, detail=str(e))

    propositions_by_question: dict[int, list] = {}
    for row in proposition_rows:
        qid = int(row["id_question"])
        propositions_by_question.setdefault(qid, []).append(
            KnowledgeOverviewProposition(
                id_proposition=int(row["id_proposition"]),
                date_creation=_format_date_creation(row.get("date_creation")),
            )
        )

    evaluations_by_question: dict[int, list] = {}
    for row in evaluation_rows:
        qid = int(row["id_question"])
        evaluations_by_question.setdefault(qid, []).append(
            KnowledgeOverviewEvaluation(
                id_evaluation=int(row["id_evaluation"]),
                date_creation=_format_date_creation(row.get("date_creation")),
            )
        )

    questions_by_subtheme: dict[int, list] = {}
    for row in question_rows:
        sid = row.get("id_subtheme")
        if sid is None:
            continue
        sid_int = int(sid)
        qid = int(row["id_question"])
        raw_label = (row.get("libelle") or "").strip()
        try:
            from urllib.parse import unquote

            label = unquote(raw_label).replace("''", "'") if raw_label else f"Question {qid}"
        except Exception:
            label = raw_label.replace("''", "'") if raw_label else f"Question {qid}"
        questions_by_subtheme.setdefault(sid_int, []).append(
            KnowledgeOverviewQuestion(
                id_question=qid,
                label=label,
                propositions=propositions_by_question.get(qid, []),
                evaluations=evaluations_by_question.get(qid, []),
            )
        )

    subthemes_by_theme: dict[int, list] = {}
    for row in subtheme_rows:
        tid = int(row["id_theme"])
        sid_int = int(row["id_subtheme"])
        subthemes_by_theme.setdefault(tid, []).append(
            KnowledgeOverviewSubTheme(
                id_subtheme=sid_int,
                label=row["label"] or f"Parcours {sid_int}",
                questions=questions_by_subtheme.get(sid_int, []),
            )
        )

    themes_by_discipline: dict[int, list] = {}
    for row in theme_rows:
        tid = int(row["id_theme"])
        did = row.get("id_discipline")
        if did is None:
            continue
        did_int = int(did)
        themes_by_discipline.setdefault(did_int, []).append(
            KnowledgeOverviewTheme(
                id_theme=tid,
                label=row["label"],
                subthemes=subthemes_by_theme.get(tid, []),
            )
        )

    return [
        KnowledgeOverviewDiscipline(
            id_discipline=int(row["id_discipline"]),
            label=row["label"],
            themes=themes_by_discipline.get(int(row["id_discipline"]), []),
        )
        for row in discipline_rows
    ]


@router.get("/{discipline_id}/detail", response_model=DisciplineDetail)
# Fait: retourne la fiche détaillée d'une discipline.
# Entrées: `discipline_id` (int).
# Retour: `DisciplineDetail`.
async def get_discipline_detail(discipline_id: int):
    try:
        rows = await postgres_select_query(
            """
            SELECT id_discipline, label, description, niveau_estime, projection
            FROM discipline
            WHERE id_discipline = $1
            """,
            discipline_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Discipline introuvable")
        base = _discipline_from_row(rows[0])

        theme_rows = await postgres_select_query(
            """
            SELECT
                id_theme,
                label,
                tagline,
                description,
                role_cognitif,
                niveau_pyramide,
                transformation_cognitive
            FROM theme
            WHERE id_discipline = $1
            ORDER BY id_theme
            """,
            discipline_id,
        )
        themes = [
            DisciplineThemeSummary(
                id_theme=r["id_theme"],
                label=r["label"],
                tagline=r.get("tagline"),
                description=r.get("description"),
                role_cognitif=r.get("role_cognitif"),
                niveau_pyramide=r.get("niveau_pyramide"),
                transformation_cognitive=r.get("transformation_cognitive"),
            )
            for r in theme_rows
        ]

        competence_rows = await postgres_select_query(
            """
            SELECT id_competence, label
            FROM competence
            WHERE id_discipline = $1
            ORDER BY label
            """,
            discipline_id,
        )
        competences = [
            DisciplineLinkedLabel(id=r["id_competence"], label=r["label"])
            for r in competence_rows
        ]

        prerequis_rows = await postgres_select_query(
            """
            SELECT id_prerequis, label
            FROM prerequis
            WHERE id_discipline = $1
            ORDER BY label
            """,
            discipline_id,
        )
        prerequis = [
            DisciplineLinkedLabel(id=r["id_prerequis"], label=r["label"])
            for r in prerequis_rows
        ]

        return DisciplineDetail(
            **base.model_dump(),
            themes=themes,
            competences=competences,
            prerequis=prerequis,
        )
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR get_discipline_detail:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# Fait: compte le nombre de parcours rattachés à une discipline.
# Entrées: `discipline_id` (int).
# Retour: `int`.
async def _count_parcours_for_discipline(discipline_id: int) -> int:
    """Parcours = lignes subtheme rattachées aux thèmes de la discipline."""
    rows = await postgres_select_query(
        """
        SELECT COUNT(s.id_subtheme)::int AS n
        FROM subtheme s
        INNER JOIN theme t ON t.id_theme = s.id_theme
        WHERE t.id_discipline = $1
        """,
        discipline_id,
    )
    return int(rows[0]["n"]) if rows else 0


@router.delete("/{disciplineId}", status_code=204)
# Fait: supprime une discipline si aucun parcours n'y est rattaché.
# Entrées: `disciplineId` (int).
# Retour: `None`.
async def delete_discipline(disciplineId: int):
    try:
        parcours_count = await _count_parcours_for_discipline(disciplineId)
        if parcours_count > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Suppression impossible : {parcours_count} parcours encore "
                    "rattaché(s) à cette discipline."
                ),
            )
        await database.postgres_delete_query(
            "DELETE FROM discipline WHERE id_discipline = $1",
            disciplineId
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.put("/{disciplineId}", response_model=Discipline)
# Fait: met à jour les champs éditables d'une discipline.
# Entrées: `disciplineId` (int), `body` (`UpdateDisciplinePayload`).
# Retour: `Discipline`.
async def update_discipline(disciplineId: int, body: UpdateDisciplinePayload):
    label = body.label.strip()
    description = (body.description or "").strip() or None
    projection = (body.projection or "").strip() or None
    niveau = body.niveau_estime
    try:
        rows = await postgres_select_query(
            """
            UPDATE discipline
            SET label = $1,
                description = $2,
                niveau_estime = $3,
                projection = $4
            WHERE id_discipline = $5
            RETURNING id_discipline, label, description, niveau_estime, projection
            """,
            label,
            description,
            niveau,
            projection,
            disciplineId,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Discipline introuvable")
        return _discipline_from_row(rows[0])
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR update_discipline:", e)
        raise HTTPException(status_code=500, detail=str(e))




