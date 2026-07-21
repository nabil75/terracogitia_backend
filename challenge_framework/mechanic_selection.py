"""Sélection de mécanique de jeu selon la matrice de compatibilité."""

from __future__ import annotations

from queries import postgres_select_query

# Mécaniques réellement jouables dans l'UI Discover (popup / play).
_UI_MECHANIC_PRIORITY = (
    "comparator",
    "sorting_lab",
    "knowledge_bridges",
    "sequence_frieze",
    "missing_fragment",
    "transform_atelier",
    "matching",
    "sorting",
    "drag_drop",
    "timed",
    "memory",
    "puzzle",
    "investigation",
    "simulation",
    "construction",
    "strategy",
    "sandbox",
    "resource_management",
)

# Sous-ensemble effectivement implémenté côté frontend.
_PLAYABLE_MECHANICS = frozenset(
    {
        "matching",
        "sorting",
        "drag_drop",
        "memory",
        "investigation",
        "comparator",
        "sorting_lab",
        "knowledge_bridges",
        "sequence_frieze",
        "missing_fragment",
        "transform_atelier",
    }
)


def _sort_by_ui_priority(options: list[tuple[str, int]]) -> list[tuple[str, int]]:
    order = {key: idx for idx, key in enumerate(_UI_MECHANIC_PRIORITY)}
    return sorted(options, key=lambda item: (order.get(item[0], 999), -item[1], item[0]))


async def count_generated_challenges_for_object(
    knowledge_object_type: str,
    knowledge_object_id: int,
) -> int:
    rows = await postgres_select_query(
        """
        SELECT COUNT(*)::int AS cnt FROM (
            SELECT id_exercise FROM challenge_exercise
            WHERE knowledge_object_type = $1 AND knowledge_object_id = $2
            UNION
            SELECT id_challenge FROM cognitive_challenge
            WHERE knowledge_object_type = $1 AND knowledge_object_id = $2
        ) AS combined
        """,
        knowledge_object_type,
        knowledge_object_id,
    )
    return int(dict(rows[0])["cnt"]) if rows else 0


async def used_mechanics_for_object(
    knowledge_object_type: str,
    knowledge_object_id: int,
) -> set[str]:
    rows = await postgres_select_query(
        """
        SELECT game_mechanic FROM challenge_exercise
        WHERE knowledge_object_type = $1 AND knowledge_object_id = $2
        UNION
        SELECT game_mechanic FROM cognitive_challenge
        WHERE knowledge_object_type = $1 AND knowledge_object_id = $2
        """,
        knowledge_object_type,
        knowledge_object_id,
    )
    return {str(dict(r)["game_mechanic"]) for r in rows}


async def pick_mechanic_for_knowledge_object(
    cognitive_operation: str,
    knowledge_object_type: str,
    knowledge_object_id: int,
) -> tuple[str, int, bool]:
    """
    Choisit une mécanique compatible.
    - Premier défi pour la question : score de compatibilité maximal (3 si possible).
    - Défis suivants : meilleure mécanique non encore utilisée, score pouvant être inférieur.
    - Pour « comparer » : privilégie toujours « comparator » tant qu'elle n'a pas été jouée.
    Retourne (mechanic_key, compatibility_score, is_first_for_question).
    """
    operation = (cognitive_operation or "").strip().lower()
    if not operation:
        operation = "identifier"

    rows = await postgres_select_query(
        """
        SELECT mechanic_key, score
        FROM operation_mechanic_compatibility
        WHERE operation_key = $1 AND score > 0
        ORDER BY score DESC, mechanic_key
        """,
        operation,
    )
    options = [(str(dict(r)["mechanic_key"]), int(dict(r)["score"])) for r in rows]

    # Filet de sécurité si le catalogue DB n'a pas encore été re-seedé après ajout.
    if operation == "comparer" and not any(m == "comparator" for m, _ in options):
        options = [("comparator", 3), *options]
    if operation == "classer" and not any(m == "sorting_lab" for m, _ in options):
        options = [("sorting_lab", 3), *options]
    if operation == "associer" and not any(m == "knowledge_bridges" for m, _ in options):
        options = [("knowledge_bridges", 3), *options]
    if operation == "ordonner" and not any(m == "sequence_frieze" for m, _ in options):
        options = [("sequence_frieze", 3), *options]
    if operation == "completer" and not any(m == "missing_fragment" for m, _ in options):
        options = [("missing_fragment", 3), *options]
    if operation == "transformer" and not any(m == "transform_atelier" for m, _ in options):
        options = [("transform_atelier", 3), *options]

    playable = [(m, s) for m, s in options if m in _PLAYABLE_MECHANICS]
    if not playable:
        raise ValueError(
            "Aucune mécanique jouable (matching, sorting, drag_drop, memory, "
            "investigation, comparator, sorting_lab, knowledge_bridges, sequence_frieze, "
            "missing_fragment, transform_atelier) "
            f"pour « {operation} »."
        )
    options = playable
    used = await used_mechanics_for_object(knowledge_object_type, knowledge_object_id)
    is_first = len(used) == 0

    # Comparer → Comparateur expert en priorité tant qu'il n'a pas été proposé.
    if operation == "comparer":
        comparator_opts = [(m, s) for m, s in options if m == "comparator"]
        if comparator_opts and "comparator" not in used:
            return "comparator", comparator_opts[0][1], is_first

    # Classer → Laboratoire de tri en priorité tant qu'il n'a pas été proposé.
    if operation == "classer":
        lab_opts = [(m, s) for m, s in options if m == "sorting_lab"]
        if lab_opts and "sorting_lab" not in used:
            return "sorting_lab", lab_opts[0][1], is_first

    # Associer → Ponts du savoir en priorité tant qu'ils n'ont pas été proposés.
    if operation == "associer":
        bridge_opts = [(m, s) for m, s in options if m == "knowledge_bridges"]
        if bridge_opts and "knowledge_bridges" not in used:
            return "knowledge_bridges", bridge_opts[0][1], is_first

    # Ordonner → Frise à reconstituer en priorité tant qu'elle n'a pas été proposée.
    if operation == "ordonner":
        frieze_opts = [(m, s) for m, s in options if m == "sequence_frieze"]
        if frieze_opts and "sequence_frieze" not in used:
            return "sequence_frieze", frieze_opts[0][1], is_first

    # Compléter → Fragment manquant en priorité tant qu'il n'a pas été proposé.
    if operation == "completer":
        frag_opts = [(m, s) for m, s in options if m == "missing_fragment"]
        if frag_opts and "missing_fragment" not in used:
            return "missing_fragment", frag_opts[0][1], is_first

    # Transformer → Atelier des transformations en priorité tant qu'il n'a pas été proposé.
    if operation == "transformer":
        atelier_opts = [(m, s) for m, s in options if m == "transform_atelier"]
        if atelier_opts and "transform_atelier" not in used:
            return "transform_atelier", atelier_opts[0][1], is_first

    if is_first:
        max_score = max(s for _, s in options)
        candidates = _sort_by_ui_priority(
            [(m, s) for m, s in options if s == max_score]
        )
        mechanic, score = candidates[0]
        return mechanic, score, True

    unused = _sort_by_ui_priority([(m, s) for m, s in options if m not in used])
    if unused:
        mechanic, score = unused[0]
        return mechanic, score, False

    mechanic, score = _sort_by_ui_priority(options)[0]
    return mechanic, score, False
