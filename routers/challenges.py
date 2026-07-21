"""Challenge framework API routes."""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

import database

from challenge_framework.catalog_seed import PYRAMID_GUIDANCE
from challenge_framework.generator import (
    build_exercise_content,
    build_investigation_reinforcement_content,
    build_memory_reinforcement_content,
    can_build_investigation_reinforcement,
    check_knowledge_bridges_link,
    check_missing_fragment_placement,
    check_sorting_lab_placement,
    check_transform_atelier_step,
    evaluate_attempt,
    extract_memory_pair_candidates,
    load_knowledge_object_label,
    normalize_matching_content,
)
from challenge_framework.mechanic_selection import pick_mechanic_for_knowledge_object
from challenge_framework.question_intent import resolve_operation_for_question
from challenge_framework.models import (
    AttemptResultDto,
    ChallengeDto,
    CheckKnowledgeBridgesLinkPayload,
    CheckMissingFragmentPayload,
    CheckSortingLabPlacementPayload,
    CheckTransformAtelierPayload,
    CreateChallengePayload,
    EvaluationReservoirDto,
    ExerciseDto,
    GenerateExercisePayload,
    PyramidGuidanceDto,
    SaveExercisePayload,
    SubmitAttemptPayload,
)
from challenge_framework.seed_db import get_compatibility_matrix
from queries import postgres_insert_query, postgres_select_query, postgres_update_query

router = APIRouter(prefix="/challenges", tags=["challenges"])


def _xp_for_level(xp: int) -> int:
    return max(1, int(math.sqrt(max(xp, 0) / 100)) + 1)


@router.get("/catalog/cognitive-operations")
async def list_cognitive_operations():
    rows = await postgres_select_query(
        """
        SELECT operation_key AS key, family, label_fr, label_en,
               definition_fr, definition_en, evaluates_fr, evaluates_en,
               pyramid_levels, examples
        FROM cognitive_operation_catalog
        ORDER BY operation_key
        """
    )
    out = []
    for r in rows:
        d = dict(r)
        d["pyramid_levels"] = _json_list_field(d.get("pyramid_levels"))
        d["examples"] = _json_list_field(d.get("examples"))
        out.append(d)
    return out


@router.get("/catalog/game-mechanics")
async def list_game_mechanics():
    rows = await postgres_select_query(
        """
        SELECT mechanic_key AS key, label_fr, label_en,
               description_fr, description_en, advantages_fr, limitations_fr,
               compatible_operations, compatible_pyramid_levels
        FROM game_mechanic_catalog
        ORDER BY mechanic_key
        """
    )
    out = []
    for r in rows:
        d = dict(r)
        d["compatible_operations"] = _json_list_field(d.get("compatible_operations"))
        d["compatible_pyramid_levels"] = _json_list_field(d.get("compatible_pyramid_levels"))
        out.append(d)
    return out


@router.get("/catalog/compatibility-matrix")
async def compatibility_matrix():
    return await get_compatibility_matrix()


@router.get("/catalog/pyramid-guidance/{level}")
async def pyramid_guidance(level: str):
    data = PYRAMID_GUIDANCE.get(level)
    if not data:
        raise HTTPException(status_code=404, detail="Niveau pyramide inconnu")
    return PyramidGuidanceDto(pyramid_level=level, **data)


@router.get("")
async def list_challenges(
    pyramid_level: Optional[str] = None,
    cognitive_operation: Optional[str] = None,
    status: Optional[str] = "published",
):
    clauses = ["1=1"]
    params: list[Any] = []
    idx = 1
    if pyramid_level:
        clauses.append(f"pyramid_level = ${idx}")
        params.append(pyramid_level)
        idx += 1
    if cognitive_operation:
        clauses.append(f"cognitive_operation = ${idx}")
        params.append(cognitive_operation)
        idx += 1
    if status:
        clauses.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    rows = await postgres_select_query(
        f"""
        SELECT id_challenge, title, pyramid_level, cognitive_operation, game_mechanic,
               knowledge_object_type, knowledge_object_id, difficulty,
               success_criteria, evaluated_competencies, prerequisites,
               typical_errors, performance_indicators, generation_rules,
               content_payload, status
        FROM cognitive_challenge
        WHERE {' AND '.join(clauses)}
        ORDER BY id_challenge DESC
        """,
        *params,
    )
    return [_challenge_row(r) for r in rows]


@router.post("", response_model=ChallengeDto)
async def create_challenge(body: CreateChallengePayload):
    score_rows = await postgres_select_query(
        """
        SELECT score FROM operation_mechanic_compatibility
        WHERE operation_key = $1 AND mechanic_key = $2
        """,
        body.cognitive_operation,
        body.game_mechanic,
    )
    if not score_rows or dict(score_rows[0])["score"] == 0:
        raise HTTPException(status_code=400, detail="Combinaison opération × mécanique incompatible")

    new_id = await postgres_insert_query(
        """
        INSERT INTO cognitive_challenge (
            title, pyramid_level, cognitive_operation, game_mechanic,
            knowledge_object_type, knowledge_object_id, difficulty,
            success_criteria, evaluated_competencies, prerequisites,
            typical_errors, performance_indicators, generation_rules,
            content_payload, status
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,$15)
        RETURNING id_challenge
        """,
        body.title,
        body.pyramid_level,
        body.cognitive_operation,
        body.game_mechanic,
        body.knowledge_object_type,
        body.knowledge_object_id,
        body.difficulty,
        json.dumps(body.success_criteria),
        json.dumps(body.evaluated_competencies),
        json.dumps(body.prerequisites),
        json.dumps(body.typical_errors),
        json.dumps(body.performance_indicators),
        json.dumps(body.generation_rules),
        json.dumps(body.content_payload),
        body.status,
    )
    rows = await postgres_select_query(
        "SELECT * FROM cognitive_challenge WHERE id_challenge = $1",
        new_id,
    )
    return _challenge_row(rows[0])


@router.post("/generate", response_model=ExerciseDto)
async def generate_exercise(body: GenerateExercisePayload):
    mechanic: Optional[str] = (body.game_mechanic or "").strip() or None
    compatibility_score: Optional[int] = None
    is_first_for_question = False
    cognitive_operation = (body.cognitive_operation or "").strip().lower()

    try:
        label, meta = await load_knowledge_object_label(
            body.knowledge_object_type, body.knowledge_object_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    cognitive_operation = resolve_operation_for_question(label, cognitive_operation)

    async def _auto_pick() -> None:
        nonlocal mechanic, compatibility_score, is_first_for_question
        mechanic, compatibility_score, is_first_for_question = (
            await pick_mechanic_for_knowledge_object(
                cognitive_operation,
                body.knowledge_object_type,
                body.knowledge_object_id,
            )
        )

    if body.auto_select_mechanic or not mechanic:
        try:
            await _auto_pick()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        # Choix forcé : on respecte la mécanique demandée (pas de repli auto).
        catalog_rows = await postgres_select_query(
            """
            SELECT mechanic_key FROM game_mechanic_catalog
            WHERE mechanic_key = $1
            """,
            mechanic,
        )
        if not catalog_rows:
            raise HTTPException(
                status_code=400,
                detail=f"Mécanique de jeu inconnue : {mechanic}",
            )
        score_rows = await postgres_select_query(
            """
            SELECT score FROM operation_mechanic_compatibility
            WHERE operation_key = $1 AND mechanic_key = $2
            """,
            cognitive_operation,
            mechanic,
        )
        if score_rows:
            compatibility_score = int(dict(score_rows[0])["score"])
        else:
            compatibility_score = 0

    content = await build_exercise_content(
        label=label,
        object_meta=meta,
        mechanic=mechanic,
        operation=cognitive_operation,
        difficulty=body.difficulty,
        variant=body.variant,
        pyramid_level=body.pyramid_level,
        use_ai=body.use_ai,
        lang=body.lang,
        object_type=body.knowledge_object_type,
        object_id=body.knowledge_object_id,
    )
    min_score = 0.75
    if mechanic in ("matching", "investigation", "comparator", "sorting_lab", "knowledge_bridges", "sequence_frieze", "missing_fragment", "transform_atelier"):
        min_score = 0.8
    elif mechanic == "memory":
        min_score = 1.0
    success_criteria = {
        "min_score": min_score,
        "indicators": ["accuracy"],
    }
    if compatibility_score is not None:
        success_criteria["compatibility_score"] = compatibility_score

    new_id = await postgres_insert_query(
        """
        INSERT INTO challenge_exercise (
            id_challenge, id_user, knowledge_object_type, knowledge_object_id,
            pyramid_level, cognitive_operation, game_mechanic, difficulty,
            content, success_criteria, status, compatibility_score, is_first_for_question
        ) VALUES (NULL, $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, 'ready', $10, $11)
        RETURNING id_exercise
        """,
        body.id_user,
        body.knowledge_object_type,
        body.knowledge_object_id,
        body.pyramid_level,
        cognitive_operation,
        mechanic,
        body.difficulty,
        json.dumps(content),
        json.dumps(success_criteria),
        compatibility_score,
        is_first_for_question,
    )
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        new_id,
    )
    return _exercise_row(rows[0])


@router.post("/exercises/{id_exercise}/save", response_model=ChallengeDto)
async def save_exercise_as_challenge(id_exercise: int, body: SaveExercisePayload):
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    if exercise.get("id_challenge"):
        existing = await postgres_select_query(
            "SELECT * FROM cognitive_challenge WHERE id_challenge = $1",
            exercise["id_challenge"],
        )
        if existing:
            return _challenge_row(existing[0])

    content = _json_field(exercise.get("content")) or {}
    lang_fr = str(content.get("instruction_fr") or "").strip()
    lang_en = str(content.get("instruction_en") or "").strip()
    title = (body.title or lang_fr or lang_en or "Défi cognitif").strip()[:200]
    success_criteria = _json_field(exercise.get("success_criteria")) or {}

    new_id = await postgres_insert_query(
        """
        INSERT INTO cognitive_challenge (
            title, pyramid_level, cognitive_operation, game_mechanic,
            knowledge_object_type, knowledge_object_id, difficulty,
            success_criteria, evaluated_competencies, prerequisites,
            typical_errors, performance_indicators, generation_rules,
            content_payload, status
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,$14::jsonb,$15)
        RETURNING id_challenge
        """,
        title,
        exercise["pyramid_level"],
        exercise["cognitive_operation"],
        exercise["game_mechanic"],
        exercise["knowledge_object_type"],
        exercise["knowledge_object_id"],
        exercise["difficulty"],
        json.dumps(success_criteria),
        json.dumps([]),
        json.dumps([]),
        json.dumps([]),
        json.dumps(["accuracy"]),
        json.dumps({"source": "discover_save", "id_exercise": id_exercise}),
        json.dumps(content),
        body.status,
    )
    await postgres_update_query(
        "UPDATE challenge_exercise SET id_challenge = $2 WHERE id_exercise = $1",
        id_exercise,
        new_id,
    )
    saved = await postgres_select_query(
        "SELECT * FROM cognitive_challenge WHERE id_challenge = $1",
        new_id,
    )
    return _challenge_row(saved[0])


@router.get("/evaluation-reservoir", response_model=list[EvaluationReservoirDto])
async def list_evaluation_reservoir(
    id_user: Optional[int] = None,
    knowledge_object_type: Optional[str] = None,
    knowledge_object_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    clauses = ["1=1"]
    params: list[Any] = []
    idx = 1
    if id_user is not None:
        clauses.append(f"id_user = ${idx}")
        params.append(id_user)
        idx += 1
    if knowledge_object_type:
        clauses.append(f"knowledge_object_type = ${idx}")
        params.append(knowledge_object_type)
        idx += 1
    if knowledge_object_id is not None:
        clauses.append(f"knowledge_object_id = ${idx}")
        params.append(knowledge_object_id)
        idx += 1
    params.append(limit)
    rows = await postgres_select_query(
        f"""
        SELECT id_record, id_user, knowledge_object_type, knowledge_object_id,
               pyramid_level, cognitive_operation, game_mechanic,
               compatibility_score, is_first_challenge,
               id_exercise, id_attempt, id_evaluation,
               score, passed, xp_gained, mastery_delta, duration_ms,
               feedback, criteria_results, dashboard_tags, created_at
        FROM evaluation_reservoir
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC
        LIMIT ${idx}
        """,
        *params,
    )
    return [_reservoir_row(r) for r in rows]


@router.get("/exercises/by-question/{id_question}/saved")
async def list_saved_exercises_by_question(id_question: int):
    """Exercices liés à un défi enregistré (sauvegarde depuis Découverte)."""
    rows = await postgres_select_query(
        """
        SELECT e.id_exercise, e.id_challenge, e.game_mechanic, e.cognitive_operation,
               e.compatibility_score, e.is_first_for_question,
               c.title, c.created_at AS saved_at
        FROM challenge_exercise e
        INNER JOIN cognitive_challenge c ON c.id_challenge = e.id_challenge
        WHERE e.knowledge_object_type = 'question'
          AND e.knowledge_object_id = $1
        ORDER BY c.created_at DESC
        """,
        id_question,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        saved_at = d.get("saved_at")
        out.append(
            {
                "id_exercise": d["id_exercise"],
                "id_challenge": d["id_challenge"],
                "title": (d.get("title") or "Défi cognitif").strip(),
                "game_mechanic": d["game_mechanic"],
                "cognitive_operation": d["cognitive_operation"],
                "compatibility_score": d.get("compatibility_score"),
                "is_first_for_question": bool(d.get("is_first_for_question")),
                "saved_at": (
                    saved_at.isoformat()
                    if hasattr(saved_at, "isoformat")
                    else str(saved_at) if saved_at else None
                ),
            }
        )
    return out


@router.delete("/exercises/{id_exercise}/saved", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_exercise(id_exercise: int):
    """Supprime un défi enregistré depuis Découverte (exercice + enregistrement associé)."""
    if database.pool is None:
        raise HTTPException(status_code=500, detail="Pool base de données non initialisé.")
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id_exercise, id_challenge
                FROM challenge_exercise
                WHERE id_exercise = $1
                """,
                id_exercise,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Exercice introuvable.")
            id_challenge = row["id_challenge"]
            if not id_challenge:
                raise HTTPException(status_code=404, detail="Ce défi n'est pas enregistré.")
            await conn.execute(
                "DELETE FROM cognitive_challenge WHERE id_challenge = $1",
                id_challenge,
            )
            await conn.execute(
                "DELETE FROM challenge_exercise WHERE id_exercise = $1",
                id_exercise,
            )


@router.get("/exercises/{id_exercise}/memory-reinforcement/available")
async def memory_reinforcement_available(id_exercise: int):
    """Indique si un défi memory peut être dérivé de l'exercice source."""
    rows = await postgres_select_query(
        "SELECT content FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    content = _json_field(dict(rows[0]).get("content")) or {}
    pairs = extract_memory_pair_candidates(content)
    return {"available": len(pairs) >= 2, "pair_count": len(pairs)}


@router.post("/exercises/{id_exercise}/memory-reinforcement", response_model=ExerciseDto)
async def create_memory_reinforcement(id_exercise: int, lang: Optional[str] = Query(default=None)):
    """Génère un second défi memory pour renforcer les paires du défi source."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    source = dict(rows[0])
    source_content = _json_field(source.get("content")) or {}
    if str(source_content.get("mechanic") or source.get("game_mechanic")) == "memory":
        raise HTTPException(
            status_code=400,
            detail="Cet exercice est déjà un défi memory.",
        )
    try:
        memory_content = build_memory_reinforcement_content(
            source_content,
            operation=str(source.get("cognitive_operation") or "identifier"),
            source_exercise_id=id_exercise,
            lang=lang,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sc = _json_field(source.get("success_criteria")) or {}
    success_criteria = {
        "min_score": 1.0,
        "indicators": ["accuracy", "memory_efficiency"],
        "reinforcement_of": id_exercise,
        "compatibility_score": sc.get("compatibility_score"),
    }
    new_id = await postgres_insert_query(
        """
        INSERT INTO challenge_exercise (
            id_challenge, id_user, knowledge_object_type, knowledge_object_id,
            pyramid_level, cognitive_operation, game_mechanic, difficulty,
            content, success_criteria, status, compatibility_score, is_first_for_question
        ) VALUES (NULL, $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, 'ready', $10, FALSE)
        RETURNING id_exercise
        """,
        source.get("id_user"),
        source["knowledge_object_type"],
        source["knowledge_object_id"],
        source["pyramid_level"],
        source["cognitive_operation"],
        "memory",
        source.get("difficulty") or 2,
        json.dumps(memory_content),
        json.dumps(success_criteria),
        source.get("compatibility_score"),
    )
    created = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        new_id,
    )
    return _exercise_row(created[0])


async def _question_label_for_exercise(exercise: dict[str, Any]) -> str:
    if exercise.get("knowledge_object_type") != "question":
        return ""
    rows = await postgres_select_query(
        "SELECT libelle FROM question WHERE id_question = $1",
        exercise["knowledge_object_id"],
    )
    if not rows:
        return ""
    return str(dict(rows[0]).get("libelle") or "").strip()


async def _question_meta_for_exercise(exercise: dict[str, Any]) -> dict[str, Any]:
    if exercise.get("knowledge_object_type") != "question":
        return {}
    try:
        from mistral.question_mistral import load_question_context_for_ai

        return await load_question_context_for_ai(int(exercise["knowledge_object_id"]))
    except Exception:
        return {}


@router.get("/exercises/{id_exercise}/investigation-reinforcement/available")
async def investigation_reinforcement_available(id_exercise: int):
    """Indique si un défi enquête peut être dérivé de l'exercice source."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    content = _json_field(exercise.get("content")) or {}
    question_label = await _question_label_for_exercise(exercise)
    available = can_build_investigation_reinforcement(content, question_label)
    return {
        "available": available,
        "pair_count": len(extract_memory_pair_candidates(content)),
        "explanation_question": bool(question_label),
    }


@router.post("/exercises/{id_exercise}/investigation-reinforcement", response_model=ExerciseDto)
async def create_investigation_reinforcement(
    id_exercise: int, lang: Optional[str] = Query(default=None)
):
    """Génère un défi enquête (Vrai/Faux) pour renforcer la compréhension."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    source = dict(rows[0])
    source_content = _json_field(source.get("content")) or {}
    if str(source_content.get("mechanic") or source.get("game_mechanic")) == "investigation":
        raise HTTPException(status_code=400, detail="Cet exercice est déjà un défi enquête.")
    question_label = await _question_label_for_exercise(source)
    question_meta = await _question_meta_for_exercise(source)
    try:
        investigation_content = build_investigation_reinforcement_content(
            source_content,
            question_label=question_label,
            operation="expliquer",
            source_exercise_id=id_exercise,
            lang=lang,
            object_meta=question_meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sc = _json_field(source.get("success_criteria")) or {}
    success_criteria = {
        "min_score": 0.8,
        "indicators": ["accuracy", "comprehension"],
        "reinforcement_of": id_exercise,
        "compatibility_score": sc.get("compatibility_score"),
    }
    new_id = await postgres_insert_query(
        """
        INSERT INTO challenge_exercise (
            id_challenge, id_user, knowledge_object_type, knowledge_object_id,
            pyramid_level, cognitive_operation, game_mechanic, difficulty,
            content, success_criteria, status, compatibility_score, is_first_for_question
        ) VALUES (NULL, $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, 'ready', $10, FALSE)
        RETURNING id_exercise
        """,
        source.get("id_user"),
        source["knowledge_object_type"],
        source["knowledge_object_id"],
        source["pyramid_level"],
        "expliquer",
        "investigation",
        source.get("difficulty") or 2,
        json.dumps(investigation_content),
        json.dumps(success_criteria),
        source.get("compatibility_score"),
    )
    created = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        new_id,
    )
    return _exercise_row(created[0])


@router.get("/exercises/{id_exercise}", response_model=ExerciseDto)
async def get_exercise(id_exercise: int, include_solution: bool = Query(default=False)):
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    dto = _exercise_row(rows[0])
    if not include_solution and isinstance(dto.content, dict):
        safe = {**dto.content}
        safe.pop("solution", None)
        dto.content = safe
    return dto


@router.post("/exercises/{id_exercise}/check-placement")
async def check_exercise_placement(
    id_exercise: int,
    body: CheckSortingLabPlacementPayload,
):
    """Feedback immédiat pour le Laboratoire de tri (sans enregistrer de tentative)."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    content = exercise.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        content = {}
    mechanic = str(content.get("mechanic") or exercise.get("game_mechanic") or "")
    if mechanic != "sorting_lab":
        raise HTTPException(
            status_code=400,
            detail="La vérification unitaire n'est disponible que pour sorting_lab",
        )
    return check_sorting_lab_placement(
        content,
        item_id=body.item_id,
        category_id=body.category_id,
    )


@router.post("/exercises/{id_exercise}/check-link")
async def check_exercise_link(
    id_exercise: int,
    body: CheckKnowledgeBridgesLinkPayload,
):
    """Feedback immédiat pour les Ponts du savoir (sans enregistrer de tentative)."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    content = exercise.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        content = {}
    mechanic = str(content.get("mechanic") or exercise.get("game_mechanic") or "")
    if mechanic != "knowledge_bridges":
        raise HTTPException(
            status_code=400,
            detail="La vérification de lien n'est disponible que pour knowledge_bridges",
        )
    return check_knowledge_bridges_link(
        content,
        source_id=body.source_id,
        target_id=body.target_id,
    )


@router.post("/exercises/{id_exercise}/check-fragment")
async def check_exercise_fragment(
    id_exercise: int,
    body: CheckMissingFragmentPayload,
):
    """Feedback immédiat pour le Fragment manquant (sans enregistrer de tentative)."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    content = exercise.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        content = {}
    mechanic = str(content.get("mechanic") or exercise.get("game_mechanic") or "")
    if mechanic != "missing_fragment":
        raise HTTPException(
            status_code=400,
            detail="La vérification de fragment n'est disponible que pour missing_fragment",
        )
    return check_missing_fragment_placement(
        content,
        gap_id=body.gap_id,
        fragment_id=body.fragment_id,
    )


@router.post("/exercises/{id_exercise}/check-transform")
async def check_exercise_transform(
    id_exercise: int,
    body: CheckTransformAtelierPayload,
):
    """Feedback immédiat pour l'Atelier des transformations (sans enregistrer de tentative)."""
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    content = exercise.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        content = {}
    mechanic = str(content.get("mechanic") or exercise.get("game_mechanic") or "")
    if mechanic != "transform_atelier":
        raise HTTPException(
            status_code=400,
            detail="La vérification de transformation n'est disponible que pour transform_atelier",
        )
    return check_transform_atelier_step(
        content,
        tool_id=body.tool_id,
        step_index=body.step_index,
    )


@router.post("/attempts", response_model=AttemptResultDto)
async def submit_attempt(body: SubmitAttemptPayload):
    rows = await postgres_select_query(
        "SELECT * FROM challenge_exercise WHERE id_exercise = $1",
        body.id_exercise,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    exercise = dict(rows[0])
    content = exercise.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        content = {}

    result = evaluate_attempt(content, body.learner_actions)
    min_score = 0.75
    sc = exercise.get("success_criteria")
    if isinstance(sc, str):
        sc = json.loads(sc)
    if isinstance(sc, dict) and sc.get("min_score") is not None:
        min_score = float(sc["min_score"])
    passed = result["score"] >= min_score
    difficulty = int(exercise.get("difficulty") or 2)
    xp_gained = int(result["score"] * 50 * difficulty) if passed else int(result["score"] * 10)
    mastery_delta = 0.15 * result["score"] if passed else -0.05 * (1 - result["score"])

    id_attempt = await postgres_insert_query(
        """
        INSERT INTO challenge_attempt (
            id_exercise, id_user, attempt_number, learner_actions,
            duration_ms, score, mastery_delta, error_patterns
        ) VALUES (
            $1, $2,
            COALESCE((SELECT MAX(attempt_number) FROM challenge_attempt WHERE id_exercise = $1), 0) + 1,
            $3::jsonb, $4, $5, $6, $7::jsonb
        )
        RETURNING id_attempt
        """,
        body.id_exercise,
        body.id_user,
        json.dumps(body.learner_actions),
        body.duration_ms,
        result["score"],
        mastery_delta,
        json.dumps(result.get("criteria_results") or {}),
    )

    id_evaluation = await postgres_insert_query(
        """
        INSERT INTO challenge_evaluation (
            id_attempt, criteria_results, competency_scores, feedback, passed
        ) VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb, $5)
        RETURNING id_evaluation
        """,
        id_attempt,
        json.dumps(result["criteria_results"]),
        json.dumps({}),
        json.dumps(result["feedback"]),
        passed,
    )

    compatibility_score = int(exercise.get("compatibility_score") or 0)
    if isinstance(sc, dict) and sc.get("compatibility_score") is not None:
        compatibility_score = int(sc["compatibility_score"])
    is_first_challenge = bool(exercise.get("is_first_for_question"))
    dashboard_tags = [
        "challenge",
        exercise["cognitive_operation"],
        exercise["game_mechanic"],
        exercise["pyramid_level"],
    ]
    if is_first_challenge:
        dashboard_tags.append("first_challenge")

    await postgres_insert_query(
        """
        INSERT INTO evaluation_reservoir (
            id_user, knowledge_object_type, knowledge_object_id,
            pyramid_level, cognitive_operation, game_mechanic,
            compatibility_score, is_first_challenge,
            id_exercise, id_attempt, id_evaluation,
            score, passed, xp_gained, mastery_delta, duration_ms,
            feedback, criteria_results, dashboard_tags
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
            $12, $13, $14, $15, $16, $17::jsonb, $18::jsonb, $19::jsonb
        )
        RETURNING id_record
        """,
        body.id_user,
        exercise["knowledge_object_type"],
        exercise["knowledge_object_id"],
        exercise["pyramid_level"],
        exercise["cognitive_operation"],
        exercise["game_mechanic"],
        compatibility_score,
        is_first_challenge,
        body.id_exercise,
        id_attempt,
        id_evaluation,
        result["score"],
        passed,
        xp_gained,
        mastery_delta,
        body.duration_ms,
        json.dumps(result["feedback"]),
        json.dumps(result["criteria_results"]),
        json.dumps(dashboard_tags),
    )

    if body.id_user:
        await _update_mastery(
            body.id_user,
            exercise["knowledge_object_type"],
            exercise["knowledge_object_id"],
            exercise["pyramid_level"],
            exercise["cognitive_operation"],
            mastery_delta,
        )
        await _update_gamification(body.id_user, xp_gained)

    await postgres_update_query(
        "UPDATE challenge_exercise SET status = $2 WHERE id_exercise = $1",
        body.id_exercise,
        "completed" if passed else "ready",
    )

    return AttemptResultDto(
        id_attempt=id_attempt,
        id_evaluation=id_evaluation,
        score=result["score"],
        passed=passed,
        mastery_delta=mastery_delta,
        xp_gained=xp_gained,
        feedback=result["feedback"],
        criteria_results=result["criteria_results"],
    )


@router.get("/mastery")
async def get_mastery(id_user: Optional[int] = None):
    if not id_user:
        return []
    rows = await postgres_select_query(
        """
        SELECT knowledge_object_type, knowledge_object_id, pyramid_level,
               cognitive_operation, mastery_score, confidence, attempt_count, last_attempt_at
        FROM learner_mastery
        WHERE id_user = $1
        ORDER BY last_attempt_at DESC NULLS LAST
        """,
        id_user,
    )
    return [dict(r) for r in rows]


@router.get("/gamification/profile")
async def gamification_profile(id_user: Optional[int] = None):
    if not id_user:
        return {"xp_total": 0, "level": 1, "streak_days": 0, "achievements": []}
    rows = await postgres_select_query(
        "SELECT xp_total, level, streak_days FROM learner_gamification WHERE id_user = $1",
        id_user,
    )
    profile = dict(rows[0]) if rows else {"xp_total": 0, "level": 1, "streak_days": 0}
    ach = await postgres_select_query(
        """
        SELECT la.achievement_key, la.unlocked_at, ad.title_fr, ad.title_en
        FROM learner_achievement la
        JOIN achievement_definition ad ON ad.achievement_key = la.achievement_key
        WHERE la.id_user = $1
        ORDER BY la.unlocked_at DESC
        """,
        id_user,
    )
    profile["achievements"] = [dict(a) for a in ach]
    return profile


@router.get("/{id_challenge}", response_model=ChallengeDto)
async def get_challenge(id_challenge: int):
    rows = await postgres_select_query(
        "SELECT * FROM cognitive_challenge WHERE id_challenge = $1",
        id_challenge,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Défi introuvable")
    return _challenge_row(rows[0])


async def _update_mastery(
    id_user: int,
    object_type: str,
    object_id: int,
    pyramid_level: str,
    operation: str,
    delta: float,
) -> None:
    await postgres_insert_query(
        """
        INSERT INTO learner_mastery (
            id_user, knowledge_object_type, knowledge_object_id,
            pyramid_level, cognitive_operation, mastery_score, confidence, attempt_count, last_attempt_at
        ) VALUES ($1,$2,$3,$4,$5,GREATEST(0, LEAST(1, $6)), 0.5, 1, NOW())
        ON CONFLICT (id_user, knowledge_object_type, knowledge_object_id, pyramid_level, cognitive_operation)
        DO UPDATE SET
            mastery_score = GREATEST(0, LEAST(1, learner_mastery.mastery_score + $7)),
            attempt_count = learner_mastery.attempt_count + 1,
            last_attempt_at = NOW(),
            confidence = LEAST(1, learner_mastery.confidence + 0.05)
        RETURNING id_mastery
        """,
        id_user,
        object_type,
        object_id,
        pyramid_level,
        operation,
        max(0.0, min(1.0, 0.5 + delta)),
        delta,
    )


async def _update_gamification(id_user: int, xp_gained: int) -> None:
    rows = await postgres_select_query(
        "SELECT xp_total FROM learner_gamification WHERE id_user = $1",
        id_user,
    )
    current_xp = int(dict(rows[0])["xp_total"]) if rows else 0
    new_xp = current_xp + xp_gained
    new_level = _xp_for_level(new_xp)
    await postgres_insert_query(
        """
        INSERT INTO learner_gamification (id_user, xp_total, level, streak_days, last_activity_at)
        VALUES ($1, $2, $3, 1, NOW())
        ON CONFLICT (id_user) DO UPDATE SET
            xp_total = $2,
            level = $3,
            streak_days = learner_gamification.streak_days + 1,
            last_activity_at = NOW()
        RETURNING id_user
        """,
        id_user,
        new_xp,
        new_level,
    )


def _json_field(val: Any) -> Any:
    if isinstance(val, str):
        return json.loads(val)
    return val if val is not None else {}


def _json_list_field(val: Any) -> list[Any]:
    parsed = _json_field(val) if isinstance(val, str) else val
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return parsed
    return [parsed]


def _challenge_row(row: Any) -> ChallengeDto:
    d = dict(row)
    return ChallengeDto(
        id_challenge=d["id_challenge"],
        title=d["title"],
        pyramid_level=d["pyramid_level"],
        cognitive_operation=d["cognitive_operation"],
        game_mechanic=d["game_mechanic"],
        knowledge_object_type=d["knowledge_object_type"],
        knowledge_object_id=d["knowledge_object_id"],
        difficulty=d["difficulty"],
        success_criteria=_json_field(d.get("success_criteria")) or {},
        evaluated_competencies=_json_field(d.get("evaluated_competencies")) or [],
        prerequisites=_json_field(d.get("prerequisites")) or [],
        typical_errors=_json_field(d.get("typical_errors")) or [],
        performance_indicators=_json_field(d.get("performance_indicators")) or [],
        generation_rules=_json_field(d.get("generation_rules")) or {},
        content_payload=_json_field(d.get("content_payload")) or {},
        status=d["status"],
    )


def _prepare_exercise_content(content: dict[str, Any], game_mechanic: str) -> dict[str, Any]:
    if game_mechanic == "matching" and content:
        seed = content.get("solution") or content.get("pairs") or content.get("instruction_fr")
        return normalize_matching_content(dict(content), seed=seed)
    return content


def _exercise_row(row: Any) -> ExerciseDto:
    d = dict(row)
    content = _json_field(d.get("content")) or {}
    content = _prepare_exercise_content(content, str(d.get("game_mechanic") or ""))
    return ExerciseDto(
        id_exercise=d["id_exercise"],
        id_challenge=d.get("id_challenge"),
        id_user=d.get("id_user"),
        knowledge_object_type=d["knowledge_object_type"],
        knowledge_object_id=d["knowledge_object_id"],
        pyramid_level=d["pyramid_level"],
        cognitive_operation=d["cognitive_operation"],
        game_mechanic=d["game_mechanic"],
        difficulty=d["difficulty"],
        content=content,
        success_criteria=_json_field(d.get("success_criteria")) or {},
        status=d["status"],
        compatibility_score=d.get("compatibility_score"),
        is_first_for_question=bool(d.get("is_first_for_question")),
    )


def _reservoir_row(row: Any) -> EvaluationReservoirDto:
    d = dict(row)
    created = d.get("created_at")
    return EvaluationReservoirDto(
        id_record=d["id_record"],
        id_user=d.get("id_user"),
        knowledge_object_type=d["knowledge_object_type"],
        knowledge_object_id=d["knowledge_object_id"],
        pyramid_level=d["pyramid_level"],
        cognitive_operation=d["cognitive_operation"],
        game_mechanic=d["game_mechanic"],
        compatibility_score=int(d.get("compatibility_score") or 0),
        is_first_challenge=bool(d.get("is_first_challenge")),
        id_exercise=d.get("id_exercise"),
        id_attempt=d.get("id_attempt"),
        id_evaluation=d.get("id_evaluation"),
        score=float(d.get("score") or 0),
        passed=bool(d.get("passed")),
        xp_gained=int(d.get("xp_gained") or 0),
        mastery_delta=float(d.get("mastery_delta") or 0),
        duration_ms=int(d.get("duration_ms") or 0),
        feedback=_json_field(d.get("feedback")) or {},
        criteria_results=_json_field(d.get("criteria_results")) or {},
        dashboard_tags=_json_list_field(d.get("dashboard_tags")),
        created_at=created.isoformat() if hasattr(created, "isoformat") else str(created) if created else None,
    )
