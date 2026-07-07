"""
Évaluation avancée : agrégats pyramide, effort de découverte, sessions parcours.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mistral.advanced_evaluation_mistral import generate_advanced_evaluation_insights
from mistral.language_prompts import normalize_lang
from mistral.pyramid_prompts import (
    PYRAMID_LEVELS,
    cognitive_operation_family,
    normalize_cognitive_operation,
    normalize_pyramid_level,
)
from queries import postgres_insert_query, postgres_select_query, postgres_update_query

router = APIRouter(prefix="/advanced-evaluation", tags=["advanced-evaluation"])

VALID_DISCOVER_EVENTS = frozenset(
    {
        "proposition_requested",
        "proposition_saved",
        "proposition_discarded",
        "exercise_in_proposition",
    }
)


def _resolve_eval_pyramid_level(row: dict[str, Any]) -> str:
    """Niveau pyramide : question → parcours → thème."""
    for key in (
        "question_niveau_pyramide",
        "subtheme_niveau_pyramide",
        "theme_niveau_pyramide",
    ):
        level = normalize_pyramid_level(row.get(key))
        if level:
            return level
    return "faits_observables"


def _resolve_question_operation(row: dict[str, Any]) -> str | None:
    for key in ("operation_cognitive", "op_raw"):
        op = normalize_cognitive_operation(row.get(key))
        if op:
            return op
    return None


def _iso_dt(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _empty_operation_bucket(operation: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "family": cognitive_operation_family(operation),
        "propositions_requested": 0,
        "propositions_saved": 0,
        "propositions_discarded": 0,
        "exercises_in_propositions": 0,
        "first_activity_at": None,
        "available_in_discipline": False,
    }


async def _build_cognitive_discovery_profile(
    id_discipline: Optional[int] = None,
) -> dict[str, Any]:
    """Croisement opérations cognitives × activités de découverte."""
    discipline_q_filter = ""
    discipline_params: list[Any] = []
    if id_discipline is not None:
        discipline_q_filter = " AND t.id_discipline = $1"
        discipline_params = [id_discipline]

    question_rows = await postgres_select_query(
        f"""
        SELECT
            q.operation_cognitive,
            q.niveau_pyramide AS question_niveau_pyramide,
            s.niveau_pyramide AS subtheme_niveau_pyramide,
            t.niveau_pyramide AS theme_niveau_pyramide
        FROM question q
        JOIN subtheme s ON s.id_subtheme = q.id_subtheme
        JOIN theme t ON t.id_theme = s.id_theme
        WHERE 1=1{discipline_q_filter}
        """,
        *discipline_params,
    )

    available_ops: set[str] = set()
    available_by_pyramid: dict[str, set[str]] = {level: set() for level in PYRAMID_LEVELS}

    for r in question_rows:
        row = dict(r)
        op = _resolve_question_operation(row)
        if not op:
            continue
        available_ops.add(op)
        pyramid = _resolve_eval_pyramid_level(row)
        available_by_pyramid.setdefault(pyramid, set()).add(op)

    activity_discipline = ""
    activity_params: list[Any] = []
    if id_discipline is not None:
        activity_discipline = """
            AND (
                da.id_subtheme IS NULL OR da.id_subtheme IN (
                    SELECT st.id_subtheme FROM subtheme st
                    JOIN theme th ON th.id_theme = st.id_theme
                    WHERE th.id_discipline = $1
                )
            )
        """
        activity_params = [id_discipline]

    activity_detail_rows = await postgres_select_query(
        f"""
        SELECT
            da.event_type,
            da.created_at,
            q.operation_cognitive AS op_raw,
            q.niveau_pyramide AS question_niveau_pyramide,
            s.niveau_pyramide AS subtheme_niveau_pyramide,
            t.niveau_pyramide AS theme_niveau_pyramide
        FROM discover_activity da
        LEFT JOIN question q ON q.id_question = da.id_question
        LEFT JOIN subtheme s ON s.id_subtheme = COALESCE(da.id_subtheme, q.id_subtheme)
        LEFT JOIN theme t ON t.id_theme = COALESCE(da.id_theme, s.id_theme)
        WHERE da.event_type IN (
            'proposition_requested',
            'proposition_saved',
            'proposition_discarded',
            'exercise_in_proposition'
        ){activity_discipline}
        ORDER BY da.created_at ASC
        """,
        *activity_params,
    )

    op_buckets: dict[str, dict[str, Any]] = {}
    explored_ops: set[str] = set()
    matrix_counts: dict[str, dict[str, int]] = {
        level: {} for level in PYRAMID_LEVELS
    }
    first_by_op: dict[str, Any] = {}

    event_field = {
        "proposition_requested": "propositions_requested",
        "proposition_saved": "propositions_saved",
        "proposition_discarded": "propositions_discarded",
        "exercise_in_proposition": "exercises_in_propositions",
    }

    for r in activity_detail_rows:
        row = dict(r)
        op = _resolve_question_operation(row)
        if not op:
            continue
        explored_ops.add(op)
        bucket = op_buckets.setdefault(op, _empty_operation_bucket(op))
        bucket["available_in_discipline"] = op in available_ops
        event = row.get("event_type")
        field = event_field.get(event or "")
        if field:
            bucket[field] += 1
        created = row.get("created_at")
        if created and (
            bucket["first_activity_at"] is None
            or created < bucket["first_activity_at"]
        ):
            bucket["first_activity_at"] = created
        if created and (op not in first_by_op or created < first_by_op[op]):
            first_by_op[op] = created

        if event == "proposition_requested":
            pyramid = _resolve_eval_pyramid_level(row)
            matrix_counts.setdefault(pyramid, {})
            matrix_counts[pyramid][op] = matrix_counts[pyramid].get(op, 0) + 1

    for op in available_ops:
        op_buckets.setdefault(op, _empty_operation_bucket(op))
        op_buckets[op]["available_in_discipline"] = True

    operations_out = sorted(
        op_buckets.values(),
        key=lambda item: (
            -(
                item["propositions_requested"]
                + item["propositions_saved"]
                + item["propositions_discarded"]
            ),
            item["operation"],
        ),
    )
    for item in operations_out:
        item["first_activity_at"] = _iso_dt(item.get("first_activity_at"))

    discovery_sequence = []
    for rank, (op, created) in enumerate(
        sorted(first_by_op.items(), key=lambda x: x[1]), start=1
    ):
        discovery_sequence.append(
            {
                "rank": rank,
                "operation": op,
                "family": cognitive_operation_family(op),
                "first_at": _iso_dt(created),
            }
        )

    unexplored_operations = sorted(available_ops - explored_ops)

    pyramid_operation_matrix = []
    for level in PYRAMID_LEVELS:
        ops_map = matrix_counts.get(level, {})
        if not ops_map and not available_by_pyramid.get(level):
            continue
        pyramid_operation_matrix.append(
            {
                "niveau_pyramide": level,
                "discover_requested_by_operation": ops_map,
                "available_operations": sorted(available_by_pyramid.get(level, set())),
            }
        )

    family_totals: dict[str, int] = {}
    for item in operations_out:
        family = item["family"]
        total = (
            item["propositions_requested"]
            + item["propositions_saved"]
            + item["propositions_discarded"]
        )
        family_totals[family] = family_totals.get(family, 0) + total

    dominant_family = None
    if family_totals:
        dominant_family = max(family_totals.items(), key=lambda x: x[1])[0]

    def _first_family_rank(family: str) -> int | None:
        for step in discovery_sequence:
            if step["family"] == family:
                return step["rank"]
        return None

    obs_rank = _first_family_rank("observation")
    comp_rank = _first_family_rank("comprehension")
    observation_before_comprehension = None
    if obs_rank is not None and comp_rank is not None:
        observation_before_comprehension = obs_rank < comp_rank
    elif obs_rank is not None and comp_rank is None:
        observation_before_comprehension = True
    elif obs_rank is None and comp_rank is not None:
        observation_before_comprehension = False

    comprehension_explored = any(
        item["family"] == "comprehension" and item["propositions_requested"] > 0
        for item in operations_out
    )
    observation_explored = any(
        item["family"] == "observation" and item["propositions_requested"] > 0
        for item in operations_out
    )

    return {
        "operations": operations_out,
        "discovery_sequence": discovery_sequence,
        "unexplored_operations": unexplored_operations,
        "pyramid_operation_matrix": pyramid_operation_matrix,
        "profile_summary": {
            "dominant_family": dominant_family,
            "observation_before_comprehension": observation_before_comprehension,
            "comprehension_explored": comprehension_explored,
            "observation_explored": observation_explored,
            "operations_available_count": len(available_ops),
            "operations_explored_count": len(explored_ops),
        },
    }


class SubthemeSessionStartPayload(BaseModel):
    id_theme: Optional[int] = None
    id_subtheme: int
    source: str = "discover"


class SubthemeSessionEndPayload(BaseModel):
    id_session: int


class DiscoverActivityPayload(BaseModel):
    id_theme: Optional[int] = None
    id_subtheme: Optional[int] = None
    id_question: Optional[int] = None
    event_type: str
    id_proposition: Optional[int] = None
    meta: Optional[dict[str, Any]] = None


class InsightsRequestPayload(BaseModel):
    id_discipline: Optional[int] = None
    lang: Optional[Literal["fr", "en"]] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_seconds(start: Any, end: Any) -> Optional[int]:
    a, b = _parse_dt(start), _parse_dt(end)
    if not a or not b:
        return None
    return max(0, int((b - a).total_seconds()))


def _unique_strings(items: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        if raw is None:
            continue
        if isinstance(raw, list):
            for sub in raw:
                s = str(sub).strip()
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)
            continue
        s = str(raw).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


@router.post("/subtheme-session/start", status_code=201)
async def start_subtheme_session(payload: SubthemeSessionStartPayload):
    try:
        session_id = await postgres_insert_query(
            """
            INSERT INTO subtheme_session (id_theme, id_subtheme, source)
            VALUES ($1, $2, $3)
            RETURNING id_session
            """,
            payload.id_theme,
            payload.id_subtheme,
            (payload.source or "discover").strip() or "discover",
        )
        row = await postgres_select_query(
            """
            SELECT id_session, id_theme, id_subtheme, entered_at, source
            FROM subtheme_session WHERE id_session = $1
            """,
            session_id,
        )
        return dict(row[0]) if row else {"id_session": session_id}
    except Exception as e:
        print("ERROR start_subtheme_session:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/subtheme-session/end")
async def end_subtheme_session(payload: SubthemeSessionEndPayload):
    try:
        rows = await postgres_select_query(
            """
            SELECT id_session, entered_at, exited_at
            FROM subtheme_session WHERE id_session = $1
            """,
            payload.id_session,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        row = dict(rows[0])
        if row.get("exited_at"):
            return row
        exited = _utc_now()
        entered = row.get("entered_at")
        duration = None
        if entered:
            duration = max(0, int((exited - entered).total_seconds()))
        await postgres_update_query(
            """
            UPDATE subtheme_session
            SET exited_at = $2, duration_seconds = $3
            WHERE id_session = $1
            """,
            payload.id_session,
            exited,
            duration,
        )
        updated = await postgres_select_query(
            """
            SELECT id_session, id_theme, id_subtheme, entered_at, exited_at,
                   duration_seconds, source
            FROM subtheme_session WHERE id_session = $1
            """,
            payload.id_session,
        )
        return dict(updated[0]) if updated else {}
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR end_subtheme_session:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/discover-activity", status_code=201)
async def log_discover_activity(payload: DiscoverActivityPayload):
    event = (payload.event_type or "").strip()
    if event not in VALID_DISCOVER_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"event_type invalide. Valeurs : {sorted(VALID_DISCOVER_EVENTS)}",
        )
    meta_json = json.dumps(payload.meta, ensure_ascii=False) if payload.meta else None
    try:
        activity_id = await postgres_insert_query(
            """
            INSERT INTO discover_activity (
                id_theme, id_subtheme, id_question, event_type, id_proposition, meta
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            RETURNING id_activity
            """,
            payload.id_theme,
            payload.id_subtheme,
            payload.id_question,
            event,
            payload.id_proposition,
            meta_json,
        )
        return {"id_activity": activity_id, "event_type": event}
    except Exception as e:
        print("ERROR log_discover_activity:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def _build_overview(id_discipline: Optional[int] = None) -> dict:
    discipline_filter = ""
    params: list[Any] = []
    if id_discipline is not None:
        discipline_filter = " AND t.id_discipline = $1"
        params = [id_discipline]

    eval_rows = await postgres_select_query(
        f"""
        SELECT
            e.id_evaluation,
            e.note,
            e.pertinence_note,
            e.precision_note,
            e.clarte_note,
            e.synthese_points_forts,
            e.synthese_points_faibles,
            e.synthese_conseils_pedagogiques,
            e.date_creation,
            q.niveau_pyramide AS question_niveau_pyramide,
            s.niveau_pyramide AS subtheme_niveau_pyramide,
            t.niveau_pyramide AS theme_niveau_pyramide,
            q.operation_cognitive,
            s.label AS subtheme_label,
            t.label AS theme_label
        FROM evaluation e
        JOIN question q ON q.id_question = e.id_question
        JOIN subtheme s ON s.id_subtheme = e.id_subtheme
        JOIN theme t ON t.id_theme = e.id_theme
        WHERE 1=1{discipline_filter}
        ORDER BY e.id_evaluation DESC
        """,
        *params,
    )

    pyramid_map: dict[str, dict] = {
        level: {
            "niveau_pyramide": level,
            "evaluation_count": 0,
            "avg_note": None,
            "avg_pertinence": None,
            "avg_precision": None,
            "avg_clarte": None,
            "notes": [],
            "pertinence_notes": [],
            "precision_notes": [],
            "clarte_notes": [],
        }
        for level in PYRAMID_LEVELS
    }

    all_forts: list[str] = []
    all_faibles: list[str] = []
    all_conseils: list[str] = []

    for r in eval_rows:
        row = dict(r)
        level = _resolve_eval_pyramid_level(row)
        bucket = pyramid_map.setdefault(
            level,
            {
                "niveau_pyramide": level,
                "evaluation_count": 0,
                "avg_note": None,
                "notes": [],
                "pertinence_notes": [],
                "precision_notes": [],
                "clarte_notes": [],
            },
        )
        bucket["evaluation_count"] += 1
        for key, src in (
            ("notes", "note"),
            ("pertinence_notes", "pertinence_note"),
            ("precision_notes", "precision_note"),
            ("clarte_notes", "clarte_note"),
        ):
            val = row.get(src)
            if val is not None:
                try:
                    bucket[key].append(float(val))
                except (TypeError, ValueError):
                    pass
        all_forts.extend(_unique_strings([row.get("synthese_points_forts")]))
        all_faibles.extend(_unique_strings([row.get("synthese_points_faibles")]))
        all_conseils.extend(_unique_strings([row.get("synthese_conseils_pedagogiques")]))

    pyramid: list[dict] = []
    for level in PYRAMID_LEVELS:
        b = pyramid_map[level]
        def _avg(arr: list) -> Optional[float]:
            return round(sum(arr) / len(arr), 1) if arr else None
        pyramid.append(
            {
                "niveau_pyramide": level,
                "evaluation_count": b["evaluation_count"],
                "avg_note": _avg(b["notes"]),
                "avg_pertinence": _avg(b["pertinence_notes"]),
                "avg_precision": _avg(b["precision_notes"]),
                "avg_clarte": _avg(b["clarte_notes"]),
            }
        )

    session_params: list[Any] = []
    session_discipline = ""
    if id_discipline is not None:
        session_discipline = """
            AND s.id_subtheme IN (
                SELECT st.id_subtheme FROM subtheme st
                JOIN theme th ON th.id_theme = st.id_theme
                WHERE th.id_discipline = $1
            )
        """
        session_params = [id_discipline]

    session_rows = await postgres_select_query(
        f"""
        SELECT
            ss.id_session,
            ss.id_theme,
            ss.id_subtheme,
            ss.entered_at,
            ss.exited_at,
            ss.duration_seconds,
            ss.source,
            s.label AS subtheme_label,
            t.label AS theme_label
        FROM subtheme_session ss
        LEFT JOIN subtheme s ON s.id_subtheme = ss.id_subtheme
        LEFT JOIN theme t ON t.id_theme = ss.id_theme
        WHERE 1=1{session_discipline}
        ORDER BY ss.entered_at DESC
        LIMIT 200
        """,
        *session_params,
    )

    sessions_out = []
    total_duration = 0
    subthemes_seen: set[int] = set()
    for r in session_rows:
        row = dict(r)
        sid = row.get("id_subtheme")
        if sid is not None:
            subthemes_seen.add(int(sid))
        dur = row.get("duration_seconds")
        if dur is None and row.get("entered_at") and row.get("exited_at"):
            dur = _duration_seconds(row["entered_at"], row["exited_at"])
        if dur:
            total_duration += int(dur)
        sessions_out.append(
            {
                "id_session": row.get("id_session"),
                "id_theme": row.get("id_theme"),
                "id_subtheme": row.get("id_subtheme"),
                "theme_label": row.get("theme_label"),
                "subtheme_label": row.get("subtheme_label"),
                "entered_at": row.get("entered_at").isoformat()
                if hasattr(row.get("entered_at"), "isoformat")
                else row.get("entered_at"),
                "exited_at": row.get("exited_at").isoformat()
                if hasattr(row.get("exited_at"), "isoformat")
                else row.get("exited_at"),
                "duration_seconds": dur,
                "source": row.get("source"),
            }
        )

    activity_params: list[Any] = []
    activity_discipline = ""
    if id_discipline is not None:
        activity_discipline = """
            AND (
                da.id_subtheme IS NULL OR da.id_subtheme IN (
                    SELECT st.id_subtheme FROM subtheme st
                    JOIN theme th ON th.id_theme = st.id_theme
                    WHERE th.id_discipline = $1
                )
            )
        """
        activity_params = [id_discipline]

    activity_rows = await postgres_select_query(
        f"""
        SELECT event_type, COUNT(*)::int AS cnt
        FROM discover_activity da
        WHERE 1=1{activity_discipline}
        GROUP BY event_type
        """,
        *activity_params,
    )
    activity_counts = {dict(r)["event_type"]: dict(r)["cnt"] for r in activity_rows}

    cognitive_discovery = await _build_cognitive_discovery_profile(id_discipline)

    return {
        "pyramid": pyramid,
        "acquis": all_forts[:12],
        "points_a_travailler": all_faibles[:12],
        "conseils_pedagogiques": all_conseils[:8],
        "discover_effort": {
            "subtheme_sessions": sessions_out,
            "subthemes_explored_count": len(subthemes_seen),
            "total_duration_seconds": total_duration,
            "propositions_requested": activity_counts.get("proposition_requested", 0),
            "propositions_saved": activity_counts.get("proposition_saved", 0),
            "propositions_discarded": activity_counts.get("proposition_discarded", 0),
            "exercises_in_propositions": activity_counts.get("exercise_in_proposition", 0),
        },
        "cognitive_discovery": cognitive_discovery,
        "evaluation_total": len(eval_rows),
    }


@router.get("/overview")
async def get_advanced_evaluation_overview(id_discipline: Optional[int] = None):
    try:
        return await _build_overview(id_discipline)
    except Exception as e:
        print("ERROR get_advanced_evaluation_overview:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/insights")
async def post_advanced_evaluation_insights(body: InsightsRequestPayload):
    try:
        overview = await _build_overview(body.id_discipline)
        raw = await generate_advanced_evaluation_insights(
            overview, lang=normalize_lang(body.lang)
        )
        if isinstance(raw, str):
            raise HTTPException(status_code=502, detail=raw)
        return {"overview": overview, "insights": raw}
    except HTTPException:
        raise
    except Exception as e:
        print("ERROR post_advanced_evaluation_insights:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
