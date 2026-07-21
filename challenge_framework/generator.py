"""Exercise content generation (rule-based v1 + optional Mistral IA)."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Any

_DRAG_INSTRUCTION_RE = re.compile(
    r"(?i)"
    r"(\bgliss|\bdépos|\bdrag\b|\bdrop\b|\bslide\b|"
    r"\bdroite\b|\bgauche\b|"
    r"vers ceux de gauche|éléments de droite|"
    r"from (the )?right|to (the )?left|"
    r"right column|left column|"
    r"former les bonnes paires|form (the )?correct pairs)"
)

_GENERIC_CHALLENGE_TOKEN_RE = re.compile(
    r"(?i)^(?:"
    r"cat[ée]gorie\s+[a-z]|"
    r"zone\s+(?:principale|secondaire)|"
    r"[ée]l[ée]ment\s+[a-z]|"
    r"concept\s+central|"
    r"step\s+\d+|"
    r"[ée]tape\s+\d+"
    r")$"
)

_FILENAME_IN_LABEL_RE = re.compile(
    r"\b([\w.-]+\.(?:py|js|ts|tsx|html|css|json|yaml|yml|md))\b",
    re.I,
)

logger = logging.getLogger(__name__)


async def load_knowledge_object_label(
    object_type: str, object_id: int
) -> tuple[str, dict[str, Any]]:
    if object_type == "question":
        from mistral.question_mistral import load_question_context_for_ai

        row = await load_question_context_for_ai(object_id)
        return row.get("libelle") or f"Question {object_id}", row
    return f"Objet {object_type} #{object_id}", {}


async def build_exercise_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    mechanic: str,
    operation: str,
    difficulty: int,
    variant: str | None,
    pyramid_level: str | None = None,
    use_ai: bool | None = None,
    lang: str | None = None,
    object_type: str = "question",
    object_id: int | None = None,
) -> dict[str, Any]:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    should_use_ai = use_ai if use_ai is not None else bool(api_key)
    # Comparateur / laboratoire de tri / ponts du savoir : contenu rule-based.
    if mechanic in ("comparator", "sorting_lab", "knowledge_bridges", "sequence_frieze", "missing_fragment", "transform_atelier"):
        should_use_ai = False
    if should_use_ai and object_type == "question" and object_id is not None:
        try:
            from mistral.question_mistral import (
                generate_challenge_exercise_with_ai,
                load_question_context_for_ai,
            )

            ctx = object_meta if object_meta.get("id_question") else await load_question_context_for_ai(object_id)
            ai_content = await generate_challenge_exercise_with_ai(
                question_context=ctx,
                mechanic=mechanic,
                operation=operation,
                pyramid_level=pyramid_level or ctx.get("niveau_pyramide") or "faits_observables",
                difficulty=difficulty,
                lang=lang,
            )
            ai_content["generated_by"] = "mistral"
            return ai_content
        except Exception as exc:
            logger.warning(
                "Génération IA exercice échouée (question %s, mécanique %s) : %s",
                object_id,
                mechanic,
                exc,
            )

    rng = random.Random(variant or label)
    items = _fallback_items_from_context(label, object_meta, operation, rng)
    item_count = min(3 + difficulty, len(items))
    items = items[:item_count]

    if mechanic == "matching":
        ts_match = _fallback_typescript_matching_content(items, operation, label, variant)
        if ts_match:
            ts_match["generated_by"] = "rule_based"
            return ts_match
        left = items[: max(2, len(items) - 1)] if len(items) > 2 else items[:2]
        right = left.copy()
        rng.shuffle(right)
        content = {
            "mechanic": "matching",
            "operation": operation,
            "instruction_fr": _fallback_instruction_fr("matching", operation, label),
            "instruction_en": _fallback_instruction_en("matching", operation, label),
            "pairs": [{"left": left[i], "right": right[i]} for i in range(len(left))],
            "solution": {left[i]: right[i] for i in range(len(left))},
        }
        content = normalize_matching_content(content, seed=variant or label)
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "sorting":
        ordered = sorted(items, key=lambda x: x.lower())
        shuffled = ordered.copy()
        rng.shuffle(shuffled)
        content = {
            "mechanic": "sorting",
            "operation": operation,
            "instruction_fr": "Classez les éléments dans le bon ordre.",
            "instruction_en": "Sort the items in the correct order.",
            "items": shuffled,
            "solution": ordered,
        }
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "investigation":
        content = build_investigation_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "comparator":
        content = build_comparator_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "sorting_lab":
        content = build_sorting_lab_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "knowledge_bridges":
        content = build_knowledge_bridges_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "sequence_frieze":
        content = build_sequence_frieze_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "missing_fragment":
        content = build_missing_fragment_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "transform_atelier":
        content = build_transform_atelier_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    if mechanic == "drag_drop":
        zones = _fallback_zones_for_context(label, object_meta, operation, items)
        draggable = [
            item
            for item in items
            if item not in zones and item.lower() not in {z.lower() for z in zones}
        ]
        if not draggable:
            draggable = [item for item in items if not re.match(r"let\s+", item, flags=re.IGNORECASE)] or items
        content = {
            "mechanic": "drag_drop",
            "operation": operation,
            "instruction_fr": _fallback_instruction_fr(mechanic, operation, label),
            "instruction_en": _fallback_instruction_en(mechanic, operation, label),
            "items": draggable,
            "zones": zones,
            "solution": _fallback_drag_drop_solution(draggable, zones),
        }
        content["generated_by"] = "rule_based"
        return content

    # Repli : enquête pour expliquer, sinon drag_drop contextualisé.
    if operation == "expliquer":
        content = build_investigation_content(
            label=label,
            object_meta=object_meta,
            operation=operation,
            difficulty=difficulty,
            variant=variant,
            lang=lang,
        )
        content["generated_by"] = "rule_based"
        return content

    mechanic = "drag_drop"
    zones = _fallback_zones_for_context(label, object_meta, operation, items)
    content = {
        "mechanic": "drag_drop",
        "operation": operation,
        "instruction_fr": _fallback_instruction_fr("drag_drop", operation, label),
        "instruction_en": _fallback_instruction_en("drag_drop", operation, label),
        "items": items,
        "zones": zones,
        "solution": _fallback_drag_drop_solution(items, zones),
    }
    content["generated_by"] = "rule_based"
    return content


def _is_generic_challenge_token(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    if _GENERIC_CHALLENGE_TOKEN_RE.match(value):
        return True
    if re.search(r"(?i)^élément lié à ", value):
        return True
    return False


def _filter_contextual_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    filtered: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for left, right in pairs:
        if _is_generic_challenge_token(left) or _is_generic_challenge_token(right):
            continue
        key = (left, right)
        if key in seen:
            continue
        seen.add(key)
        filtered.append(key)
    return filtered


def _django_file_role_statements(entity: str) -> list[tuple[str, str, bool]]:
    """Affirmations Vrai/Faux contextualisées pour les fichiers Django courants."""
    key = entity.strip().lower()
    catalog: dict[str, list[tuple[str, str, bool]]] = {
        "manage.py": [
            (
                "manage.py est le point d'entrée pour exécuter des commandes Django depuis le terminal.",
                "manage.py is the entry point for running Django management commands from the terminal.",
                True,
            ),
            (
                "manage.py permet notamment de lancer le serveur de développement et d'appliquer les migrations.",
                "manage.py is used to start the development server and apply database migrations.",
                True,
            ),
            (
                "manage.py contient les définitions des routes URL de l'application.",
                "manage.py contains the application's URL route definitions.",
                False,
            ),
            (
                "manage.py remplace entièrement settings.py pour configurer le projet.",
                "manage.py entirely replaces settings.py for project configuration.",
                False,
            ),
        ],
        "settings.py": [
            (
                "settings.py centralise la configuration du projet Django.",
                "settings.py centralizes the Django project's configuration.",
                True,
            ),
            (
                "settings.py sert à lancer des commandes administratives en ligne de commande.",
                "settings.py is used to run administrative commands from the command line.",
                False,
            ),
        ],
        "urls.py": [
            (
                "urls.py mappe les chemins URL vers les vues de l'application.",
                "urls.py maps URL paths to application views.",
                True,
            ),
            (
                "urls.py exécute directement les migrations de base de données.",
                "urls.py directly runs database migrations.",
                False,
            ),
        ],
        "wsgi.py": [
            (
                "wsgi.py expose l'application Django aux serveurs web en production.",
                "wsgi.py exposes the Django application to production web servers.",
                True,
            ),
            (
                "wsgi.py remplace manage.py pour toutes les commandes de développement.",
                "wsgi.py replaces manage.py for all development commands.",
                False,
            ),
        ],
    }
    return catalog.get(key, [])


def _role_investigation_statements(
    entity: str,
    label: str,
    object_meta: dict[str, Any],
) -> list[tuple[str, str, bool]]:
    from challenge_framework.question_intent import is_role_question

    lower_label = label.lower()
    entity_lower = entity.strip().lower()
    statements: list[tuple[str, str, bool]] = []

    if "django" in lower_label or entity_lower.endswith(".py"):
        statements.extend(_django_file_role_statements(entity))

    if statements:
        return statements

    if not is_role_question(label):
        return []

    return [
        (
            f"« {entity} » remplit un rôle précis dans le contexte étudié.",
            f"\"{entity}\" plays a specific role in the studied context.",
            True,
        ),
        (
            f"« {entity} » n'a aucun rôle fonctionnel dans le contexte étudié.",
            f"\"{entity}\" has no functional role in the studied context.",
            False,
        ),
        (
            f"Comprendre le rôle de « {entity} » aide à utiliser correctement le système étudié.",
            f"Understanding the role of \"{entity}\" helps use the studied system correctly.",
            True,
        ),
    ]


def _fallback_items_from_context(
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    rng: random.Random,
) -> list[str]:
    """Construit des items à partir de la question (évite les placeholders génériques)."""
    items: list[str] = []
    concepts = object_meta.get("concepts_vises")
    if isinstance(concepts, list):
        for raw in concepts:
            if isinstance(raw, str) and raw.strip():
                items.append(raw.strip())

    for match in re.finditer(r"let\s+\w+\s*=\s*[^?;\n]+", label, flags=re.IGNORECASE):
        snippet = match.group(0).strip()
        if snippet and snippet not in items:
            items.append(snippet)

    for match in _FILENAME_IN_LABEL_RE.finditer(label):
        filename = match.group(1).strip()
        if filename and filename not in items:
            items.append(filename)

    lower = label.lower()
    type_hints = []
    if any(k in lower for k in ("typescript", "type", "string", "number", "boolean", "chaîne")):
        type_hints = ["string", "number", "boolean"]
    elif operation not in ("expliquer",) and operation in ("comparer", "classer", "identifier"):
        type_hints = ["Catégorie A", "Catégorie B", "Catégorie C"]

    for hint in type_hints:
        if hint not in items:
            items.append(hint)

    proposition = str(object_meta.get("proposition_summary") or "").strip()
    if proposition and len(items) < 4:
        for sentence in re.split(r"[.!?]\s+", proposition):
            s = sentence.strip()
            if 10 < len(s) <= 80 and s not in items:
                items.append(s)
            if len(items) >= 5:
                break

    if not items:
        items = [label[:80] if label else "Concept central"]

    items = list(dict.fromkeys(items))[: max(4, min(6, 3 + int(object_meta.get("groupe") or 2)))]
    rng.shuffle(items)
    return items


def _infer_typescript_type(snippet: str) -> str | None:
    if re.search(r"=\s*['\"]", snippet):
        return "string"
    if re.search(r"=\s*true\b", snippet, flags=re.IGNORECASE) or re.search(
        r"=\s*false\b", snippet, flags=re.IGNORECASE
    ):
        return "boolean"
    if re.search(r"=\s*-?\d+(?:\.\d+)?\b", snippet):
        return "number"
    return None


def _fallback_typescript_matching_content(
    items: list[str],
    operation: str,
    label: str,
    variant: str | None,
) -> dict[str, Any] | None:
    code_items = [item for item in items if re.match(r"let\s+", item, flags=re.IGNORECASE)]
    if len(code_items) < 2:
        return None
    solution: dict[str, str] = {}
    for code in code_items:
        inferred = _infer_typescript_type(code)
        if inferred:
            solution[code] = inferred
    if len(solution) < 2:
        return None
    content = {
        "mechanic": "matching",
        "operation": operation,
        "instruction_fr": _fallback_instruction_fr("matching", operation, label),
        "instruction_en": _fallback_instruction_en("matching", operation, label),
        "pairs": [{"left": left, "right": solution[left]} for left in solution],
        "solution": solution,
    }
    return normalize_matching_content(content, seed=variant or label)


def _fallback_zones_for_context(
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    items: list[str],
) -> list[str]:
    lower = label.lower()
    if any(k in lower for k in ("typescript", "type", "string", "number", "boolean")):
        return ["string", "number", "boolean"]
    if operation == "comparer":
        return ["Élément A", "Élément B"]
    if operation == "expliquer":
        for match in _FILENAME_IN_LABEL_RE.finditer(label):
            filename = match.group(1).strip()
            if filename:
                return [f"Rôle de {filename}", "Autre composant"]
    concepts = object_meta.get("concepts_vises")
    if isinstance(concepts, list) and len(concepts) >= 2:
        return [str(concepts[0]).strip(), str(concepts[1]).strip()]
    return ["Zone principale", "Zone secondaire"]


def _fallback_drag_drop_solution(items: list[str], zones: list[str]) -> dict[str, str]:
    solution: dict[str, str] = {}
    for item in items:
        if item in zones:
            solution[item] = item
            continue
        inferred = _infer_typescript_type(item)
        if inferred and inferred in zones:
            solution[item] = inferred
            continue
        lower_item = item.lower()
        zone_match = next((z for z in zones if z.lower() == lower_item), None)
        if zone_match:
            solution[item] = zone_match
    if len(solution) >= 2:
        return solution

    primary = zones[0] if zones else "Zone principale"
    secondary = zones[1] if len(zones) > 1 else primary
    for index, item in enumerate(items):
        if item in solution:
            continue
        solution[item] = primary if index % 2 == 0 else secondary
    return solution


def _strip_drag_instruction_sentences(text: str) -> str:
    """Retire les phrases évoquant un glisser-déposer (incompatible avec l'UI matching)."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned
    parts = re.split(r"(?<=[.!?…])\s+", cleaned)
    kept = [part.strip() for part in parts if part.strip() and not _DRAG_INSTRUCTION_RE.search(part)]
    return " ".join(kept).strip()


def sanitize_matching_instructions(content: dict[str, Any]) -> dict[str, Any]:
    """Assure des consignes compatibles avec l'interface matching (pastilles cliquables)."""
    operation = str(content.get("operation") or "")
    for key, fallback in (
        ("instruction_fr", _fallback_instruction_fr),
        ("instruction_en", _fallback_instruction_en),
    ):
        raw = str(content.get(key) or "").strip()
        cleaned = _strip_drag_instruction_sentences(raw)
        if not cleaned or _DRAG_INSTRUCTION_RE.search(cleaned):
            cleaned = fallback("matching", operation, "")
        content[key] = cleaned
    return content


def _fallback_instruction_fr(mechanic: str, operation: str, label: str) -> str:
    if mechanic == "investigation":
        return (
            "Répondez Vrai ou Faux à chaque affirmation pour valider votre compréhension "
            "de l'objet ou du concept étudié."
        )
    if mechanic == "matching":
        return (
            "Associez chaque élément à la bonne réponse "
            "en cliquant sur la pastille correspondante."
        )
    if mechanic == "drag_drop":
        if "typescript" in label.lower() or "type" in label.lower():
            return "Glissez chaque déclaration ou valeur vers son type TypeScript."
        if operation == "comparer":
            return "Classez chaque élément pour mettre en évidence la différence observée."
        return "Glissez chaque élément dans la zone appropriée."
    if mechanic == "sorting":
        return "Classez les éléments dans le bon ordre."
    return "Répondez à la question."


def _fallback_instruction_en(mechanic: str, operation: str, label: str) -> str:
    if mechanic == "investigation":
        return (
            "Answer True or False to each statement to validate your understanding "
            "of the object or concept studied."
        )
    if mechanic == "matching":
        return "Match each item to the correct answer by clicking the corresponding pill."
    if mechanic == "drag_drop":
        if "typescript" in label.lower() or "type" in label.lower():
            return "Drag each declaration or value to its TypeScript type."
        if operation == "comparer":
            return "Place each item to highlight the observable difference."
        return "Drag each item into the appropriate zone."
    if mechanic == "sorting":
        return "Sort the items in the correct order."
    return "Answer the question."


def normalize_matching_content(
    content: dict[str, Any], *, seed: str | int | None = None
) -> dict[str, Any]:
    """Prépare choix uniques mélangés et propositions (gauche) dans un ordre non aligné aux réponses."""
    solution = content.get("solution")
    if not isinstance(solution, dict) or not solution:
        expected: dict[str, str] = {}
        pairs = content.get("pairs")
        if isinstance(pairs, list):
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                left = str(pair.get("left") or "").strip()
                right = str(pair.get("right") or "").strip()
                if left and right:
                    expected[left] = right
        solution = expected
        content["solution"] = solution

    choices = list(
        dict.fromkeys(str(v).strip() for v in solution.values() if str(v).strip())
    )
    prompts = [str(k).strip() for k in solution if str(k).strip()]

    rng = random.Random(str(seed) if seed is not None else json.dumps(sorted(solution.items())))
    shuffled_choices = choices.copy()
    rng.shuffle(shuffled_choices)
    shuffled_prompts = prompts.copy()
    rng.shuffle(shuffled_prompts)

    content["choices"] = shuffled_choices
    content["prompts"] = shuffled_prompts
    return sanitize_matching_instructions(content)


def _investigation_memory_pairs(
    source_content: dict[str, Any],
    lang: str | None = None,
) -> list[tuple[str, str]]:
    """Paires affirmation → Vrai/Faux depuis un défi enquête."""
    use_en = (lang or "").strip().lower() == "en"
    statements = source_content.get("statements")
    solution = source_content.get("solution")
    if not isinstance(statements, list) or not isinstance(solution, dict):
        return []

    pairs: list[tuple[str, str]] = []
    for stmt in statements:
        if not isinstance(stmt, dict):
            continue
        stmt_id = str(stmt.get("id") or "").strip()
        if not stmt_id or stmt_id not in solution:
            continue
        text = str(
            stmt.get("text_en" if use_en else "text_fr")
            or stmt.get("text_fr")
            or stmt.get("text")
            or ""
        ).strip()
        if not text:
            continue
        is_true = bool(solution[stmt_id])
        answer = ("True" if is_true else "False") if use_en else ("Vrai" if is_true else "Faux")
        pairs.append((text, answer))
    return pairs


def extract_memory_pair_candidates(
    source_content: dict[str, Any],
    lang: str | None = None,
) -> list[tuple[str, str]]:
    """Extrait des paires problème/réponse depuis un exercice jouable."""
    mechanic = str(source_content.get("mechanic") or "")
    pairs: list[tuple[str, str]] = []

    if mechanic == "matching":
        solution = source_content.get("solution")
        if isinstance(solution, dict):
            for left, right in solution.items():
                left_s = str(left).strip()
                right_s = str(right).strip()
                if left_s and right_s:
                    pairs.append((left_s, right_s))
        if not pairs:
            raw_pairs = source_content.get("pairs")
            if isinstance(raw_pairs, list):
                for pair in raw_pairs:
                    if not isinstance(pair, dict):
                        continue
                    left_s = str(pair.get("left") or "").strip()
                    right_s = str(pair.get("right") or "").strip()
                    if left_s and right_s:
                        pairs.append((left_s, right_s))
    elif mechanic == "drag_drop":
        solution = source_content.get("solution")
        if isinstance(solution, dict):
            for item, zone in solution.items():
                item_s = str(item).strip()
                zone_s = str(zone).strip()
                if item_s and zone_s:
                    pairs.append((item_s, zone_s))
    elif mechanic == "sorting":
        solution = source_content.get("solution")
        if isinstance(solution, list):
            for index, item in enumerate(solution):
                item_s = str(item).strip()
                if item_s:
                    step_label = f"Step {index + 1}"
                    pairs.append((item_s, step_label))
    elif mechanic == "investigation":
        pairs.extend(_investigation_memory_pairs(source_content, lang))

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for left, right in pairs:
        key = (left, right)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return _filter_contextual_pairs(deduped)


def build_memory_reinforcement_content(
    source_content: dict[str, Any],
    *,
    operation: str,
    source_exercise_id: int,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi memory (flashcards) à partir des paires du défi source."""
    pair_candidates = extract_memory_pair_candidates(source_content, lang=lang)
    if len(pair_candidates) < 2:
        raise ValueError(
            "Impossible de créer un défi memory : au moins 2 paires problème/solution requises."
        )

    rng = random.Random(f"memory-{source_exercise_id}")
    selected = pair_candidates[:]
    rng.shuffle(selected)
    selected = selected[: min(6, len(selected))]

    use_en = (lang or "").strip().lower() == "en"
    step_prefix = "Step" if use_en else "Étape"

    cards: list[dict[str, str]] = []
    solution: dict[str, list[str]] = {}
    for index, (prompt, answer) in enumerate(selected):
        pair_id = f"p{index}"
        prompt_id = f"c{index * 2}"
        answer_id = f"c{index * 2 + 1}"
        display_answer = answer
        if answer.startswith("Step ") or answer.startswith("Étape "):
            display_answer = f"{step_prefix} {index + 1}"
        cards.append({"id": prompt_id, "pair_id": pair_id, "face": prompt, "kind": "prompt"})
        cards.append({"id": answer_id, "pair_id": pair_id, "face": display_answer, "kind": "answer"})
        solution[pair_id] = [prompt_id, answer_id]

    rng.shuffle(cards)
    instruction_fr = (
        "Retournez une carte puis une autre (une carte seule se recache après 2 secondes). "
        "Chaque paire partage une couleur : si problème et solution ont la même couleur, "
        "elles disparaissent. Sinon les deux cartes se recachent. Trouvez toutes les paires."
    )
    instruction_en = (
        "Flip one card then another (a single card flips back after 2 seconds). "
        "Each pair shares a color: if problem and solution match in color, they disappear. "
        "Otherwise both cards flip back. Find all pairs to finish."
    )

    return {
        "mechanic": "memory",
        "operation": operation,
        "instruction_fr": instruction_fr,
        "instruction_en": instruction_en,
        "cards": cards,
        "solution": solution,
        "pair_count": len(selected),
        "source_exercise_id": source_exercise_id,
        "generated_by": "memory_reinforcement",
    }


def build_sequence_frieze_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi Frise à reconstituer (ordonnancement de cartes)."""
    from challenge_framework.question_intent import extract_focus_entity

    rng = random.Random(f"sequence-frieze-{variant or label}-{difficulty}")
    entity = extract_focus_entity(label, object_meta) or (label or "éléments").strip()
    topic = entity[:80]
    feedback_mode = "learning" if difficulty <= 2 else "evaluation"

    sequences = _sequence_frieze_sets(topic, label)
    seq = rng.choice(sequences)
    steps = list(seq["steps"])
    # Difficulté : plus d'étapes.
    count = max(3, min(len(steps), 3 + difficulty))
    steps = steps[:count]

    items = []
    solution: list[str] = []
    for index, step in enumerate(steps):
        item_id = f"f{index}"
        items.append(
            {
                "id": item_id,
                "label_fr": step["label_fr"],
                "label_en": step["label_en"],
                "hint_fr": step.get("hint_fr") or "",
                "hint_en": step.get("hint_en") or "",
            }
        )
        solution.append(item_id)

    pool = [item["id"] for item in items]
    rng.shuffle(pool)
    # Éviter de laisser le pool déjà dans le bon ordre.
    if pool == solution and len(pool) > 1:
        pool = pool[1:] + pool[:1]

    # Positions pré-remplies (ordonnancement partiel) à difficulté ≥ 4.
    prefilled: dict[str, str] = {}
    if difficulty >= 4 and len(solution) >= 4:
        prefilled["0"] = solution[0]
        pool = [pid for pid in pool if pid != solution[0]]

    return {
        "mechanic": "sequence_frieze",
        "operation": operation or "ordonner",
        "feedback_mode": feedback_mode,
        "axis_fr": seq.get("axis_fr") or "ordre",
        "axis_en": seq.get("axis_en") or "order",
        "instruction_fr": seq.get("instruction_fr")
        or "Replacez les cartes dans le bon ordre.",
        "instruction_en": seq.get("instruction_en")
        or "Place the cards in the correct order.",
        "items": items,
        "pool": pool,
        "prefilled": prefilled,
        "solution": solution,
    }


def _sequence_frieze_sets(topic: str, label: str) -> list[dict[str, Any]]:
    label_l = (label or "").lower()
    if re.search(r"\.(py|js|ts|html)\b", label_l) or "django" in label_l or "requête" in label_l:
        return [
            {
                "axis_fr": "procédure HTTP",
                "axis_en": "HTTP procedure",
                "instruction_fr": "Ordonnez les étapes du traitement d'une requête web.",
                "instruction_en": "Order the steps of handling a web request.",
                "steps": [
                    {
                        "label_fr": "Réception de la requête HTTP",
                        "label_en": "Receive the HTTP request",
                        "hint_fr": "Point d'entrée du cycle.",
                        "hint_en": "Entry point of the cycle.",
                    },
                    {
                        "label_fr": "Routage vers la vue",
                        "label_en": "Route to the view",
                        "hint_fr": "urls.py associe le chemin.",
                        "hint_en": "urls.py maps the path.",
                    },
                    {
                        "label_fr": "Exécution de la logique métier",
                        "label_en": "Run business logic",
                        "hint_fr": "La vue traite les données.",
                        "hint_en": "The view processes data.",
                    },
                    {
                        "label_fr": "Accès éventuel aux modèles",
                        "label_en": "Optional model access",
                        "hint_fr": "Lecture ou écriture en base.",
                        "hint_en": "Read or write in the database.",
                    },
                    {
                        "label_fr": "Construction de la réponse",
                        "label_en": "Build the response",
                        "hint_fr": "HTML, JSON ou redirection.",
                        "hint_en": "HTML, JSON, or redirect.",
                    },
                    {
                        "label_fr": "Envoi au client",
                        "label_en": "Send to the client",
                        "hint_fr": "Fin du cycle requête/réponse.",
                        "hint_en": "End of the request/response cycle.",
                    },
                ],
            }
        ]

    return [
        {
            "axis_fr": "procédure",
            "axis_en": "procedure",
            "instruction_fr": f"Replacez les étapes liées à « {topic} » dans le bon ordre.",
            "instruction_en": f"Place the steps related to “{topic}” in the correct order.",
            "steps": [
                {
                    "label_fr": f"Identifier le besoin autour de {topic}",
                    "label_en": f"Identify the need around {topic}",
                    "hint_fr": "Comprendre le problème à résoudre.",
                    "hint_en": "Understand the problem to solve.",
                },
                {
                    "label_fr": f"Préparer les éléments de {topic}",
                    "label_en": f"Prepare the elements of {topic}",
                    "hint_fr": "Rassembler les prérequis.",
                    "hint_en": "Gather the prerequisites.",
                },
                {
                    "label_fr": f"Appliquer {topic}",
                    "label_en": f"Apply {topic}",
                    "hint_fr": "Exécuter l'action centrale.",
                    "hint_en": "Execute the central action.",
                },
                {
                    "label_fr": f"Vérifier le résultat de {topic}",
                    "label_en": f"Check the result of {topic}",
                    "hint_fr": "Contrôler la cohérence.",
                    "hint_en": "Check consistency.",
                },
                {
                    "label_fr": f"Consolider ou corriger {topic}",
                    "label_en": f"Consolidate or fix {topic}",
                    "hint_fr": "Ajuster si nécessaire.",
                    "hint_en": "Adjust if needed.",
                },
            ],
        },
        {
            "axis_fr": "cause → conséquence",
            "axis_en": "cause → effect",
            "instruction_fr": "Ordonnez la chaîne cause → conséquence.",
            "instruction_en": "Order the cause → effect chain.",
            "steps": [
                {
                    "label_fr": "Cause initiale",
                    "label_en": "Initial cause",
                    "hint_fr": "Événement déclencheur.",
                    "hint_en": "Triggering event.",
                },
                {
                    "label_fr": "Effet immédiat",
                    "label_en": "Immediate effect",
                    "hint_fr": "Première conséquence observable.",
                    "hint_en": "First observable consequence.",
                },
                {
                    "label_fr": "Propagation",
                    "label_en": "Propagation",
                    "hint_fr": "L'effet se diffuse dans le système.",
                    "hint_en": "The effect spreads through the system.",
                },
                {
                    "label_fr": "Résultat final",
                    "label_en": "Final outcome",
                    "hint_fr": "État atteint à la fin.",
                    "hint_en": "State reached at the end.",
                },
            ],
        },
        {
            "axis_fr": "hiérarchie",
            "axis_en": "hierarchy",
            "instruction_fr": "Ordonnez du plus général au plus spécifique.",
            "instruction_en": "Order from most general to most specific.",
            "steps": [
                {
                    "label_fr": "Cadre général",
                    "label_en": "General frame",
                    "hint_fr": "Niveau le plus abstrait.",
                    "hint_en": "Most abstract level.",
                },
                {
                    "label_fr": "Domaine",
                    "label_en": "Domain",
                    "hint_fr": "Sous-ensemble du cadre.",
                    "hint_en": "Subset of the frame.",
                },
                {
                    "label_fr": "Concept clé",
                    "label_en": "Key concept",
                    "hint_fr": "Notion structurante.",
                    "hint_en": "Structuring notion.",
                },
                {
                    "label_fr": "Cas particulier",
                    "label_en": "Particular case",
                    "hint_fr": "Instance concrète.",
                    "hint_en": "Concrete instance.",
                },
            ],
        },
    ]


def build_missing_fragment_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi Fragment manquant (compléter des lacunes)."""
    from challenge_framework.question_intent import extract_focus_entity

    rng = random.Random(f"missing-fragment-{variant or label}-{difficulty}")
    entity = extract_focus_entity(label, object_meta) or (label or "concept").strip()
    topic = entity[:80]
    feedback_mode = "learning" if difficulty <= 2 else "evaluation"

    sets = _missing_fragment_sets(topic, label)
    chosen = rng.choice(sets)

    # Nombre de lacunes selon la difficulté (1 à 3).
    gaps_src = list(chosen["gaps"])
    gap_count = max(1, min(len(gaps_src), 1 + (difficulty // 2)))
    gaps_src = gaps_src[:gap_count]

    segments: list[dict[str, Any]] = []
    solution: dict[str, str] = {}
    fragments: list[dict[str, Any]] = []
    correct_ids: list[str] = []

    for index, gap in enumerate(gaps_src):
        gap_id = f"g{index}"
        frag_id = f"f{index}"
        before = gap.get("before") or {"fr": "", "en": ""}
        after = gap.get("after") or {"fr": "", "en": ""}
        if before.get("fr") or before.get("en"):
            segments.append(
                {
                    "type": "text",
                    "text_fr": before.get("fr") or before.get("en") or "",
                    "text_en": before.get("en") or before.get("fr") or "",
                }
            )
        segments.append({"type": "gap", "id": gap_id})
        if after.get("fr") or after.get("en"):
            segments.append(
                {
                    "type": "text",
                    "text_fr": after.get("fr") or after.get("en") or "",
                    "text_en": after.get("en") or after.get("fr") or "",
                }
            )
        fragments.append(
            {
                "id": frag_id,
                "label_fr": gap["answer_fr"],
                "label_en": gap["answer_en"],
                "hint_fr": gap.get("hint_fr") or "",
                "hint_en": gap.get("hint_en") or "",
            }
        )
        solution[gap_id] = frag_id
        correct_ids.append(frag_id)

    # Distracteurs : plus nombreux en difficulté élevée.
    distractors = list(chosen.get("distractors") or [])
    distractor_count = min(len(distractors), max(1, difficulty))
    for d_index, dist in enumerate(distractors[:distractor_count]):
        frag_id = f"d{d_index}"
        fragments.append(
            {
                "id": frag_id,
                "label_fr": dist["label_fr"],
                "label_en": dist["label_en"],
                "hint_fr": dist.get("hint_fr") or "",
                "hint_en": dist.get("hint_en") or "",
            }
        )

    pool = [f["id"] for f in fragments]
    rng.shuffle(pool)

    return {
        "mechanic": "missing_fragment",
        "operation": operation or "completer",
        "feedback_mode": feedback_mode,
        "structure_kind": chosen.get("structure_kind") or "sentence",
        "instruction_fr": chosen.get("instruction_fr")
        or "Placez les fragments manquants aux bons endroits.",
        "instruction_en": chosen.get("instruction_en")
        or "Place the missing fragments in the right gaps.",
        "segments": segments,
        "fragments": fragments,
        "pool": pool,
        "solution": solution,
    }


def _missing_fragment_sets(topic: str, label: str) -> list[dict[str, Any]]:
    label_l = (label or "").lower()
    if re.search(r"\.(py|js|ts|html)\b", label_l) or "django" in label_l or "requête" in label_l:
        return [
            {
                "structure_kind": "process",
                "instruction_fr": "Complétez le cycle de traitement d'une requête web.",
                "instruction_en": "Complete the web request handling cycle.",
                "gaps": [
                    {
                        "before": {"fr": "1. Réception → 2. ", "en": "1. Receive → 2. "},
                        "after": {"fr": " → 3. Vue → 4. Réponse", "en": " → 3. View → 4. Response"},
                        "answer_fr": "Routage (urls)",
                        "answer_en": "Routing (urls)",
                        "hint_fr": "Associe le chemin à la vue.",
                        "hint_en": "Maps the path to the view.",
                    },
                    {
                        "before": {
                            "fr": "La vue accède éventuellement aux ",
                            "en": "The view may access the ",
                        },
                        "after": {"fr": " pour lire ou écrire des données.", "en": " to read or write data."},
                        "answer_fr": "modèles",
                        "answer_en": "models",
                        "hint_fr": "Couche ORM / base de données.",
                        "hint_en": "ORM / database layer.",
                    },
                    {
                        "before": {
                            "fr": "Le résultat est renvoyé au ",
                            "en": "The result is sent back to the ",
                        },
                        "after": {"fr": ".", "en": "."},
                        "answer_fr": "client",
                        "answer_en": "client",
                        "hint_fr": "Navigateur ou appelant HTTP.",
                        "hint_en": "Browser or HTTP caller.",
                    },
                ],
                "distractors": [
                    {
                        "label_fr": "Compilation du binaire",
                        "label_en": "Binary compilation",
                        "hint_fr": "Hors du cycle requête HTTP.",
                        "hint_en": "Outside the HTTP request cycle.",
                    },
                    {
                        "label_fr": "Migration SQL manuelle",
                        "label_en": "Manual SQL migration",
                        "hint_fr": "Opération d'admin, pas le flux courant.",
                        "hint_en": "Admin task, not the normal flow.",
                    },
                    {
                        "label_fr": "Cache DNS",
                        "label_en": "DNS cache",
                        "hint_fr": "Étape réseau amont, pas applicative.",
                        "hint_en": "Upstream network step, not app-level.",
                    },
                ],
            }
        ]

    return [
        {
            "structure_kind": "sentence",
            "instruction_fr": f"Complétez la structure liée à « {topic} ».",
            "instruction_en": f"Complete the structure related to “{topic}”.",
            "gaps": [
                {
                    "before": {
                        "fr": f"Pour comprendre {topic}, on commence par ",
                        "en": f"To understand {topic}, we start by ",
                    },
                    "after": {"fr": ".", "en": "."},
                    "answer_fr": "identifier les éléments clés",
                    "answer_en": "identifying the key elements",
                    "hint_fr": "Première étape d'analyse.",
                    "hint_en": "First analysis step.",
                },
                {
                    "before": {
                        "fr": f"Ensuite, on relie ces éléments pour former ",
                        "en": f"Then we connect these elements to form ",
                    },
                    "after": {"fr": f" autour de {topic}.", "en": f" around {topic}."},
                    "answer_fr": "une structure cohérente",
                    "answer_en": "a coherent structure",
                    "hint_fr": "Le but est la cohérence d'ensemble.",
                    "hint_en": "The goal is overall coherence.",
                },
                {
                    "before": {
                        "fr": "Enfin, on vérifie que rien ",
                        "en": "Finally, we check that nothing ",
                    },
                    "after": {"fr": " dans l'ensemble.", "en": " in the whole."},
                    "answer_fr": "ne manque",
                    "answer_en": "is missing",
                    "hint_fr": "Contrôle de complétude.",
                    "hint_en": "Completeness check.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "supprimer tous les indices",
                    "label_en": "removing all clues",
                    "hint_fr": "Contre-productif pour compléter.",
                    "hint_en": "Counterproductive for completing.",
                },
                {
                    "label_fr": "ignorer le contexte",
                    "label_en": "ignoring the context",
                    "hint_fr": "Le contexte guide la lacune.",
                    "hint_en": "Context guides the gap.",
                },
                {
                    "label_fr": "mélanger au hasard",
                    "label_en": "shuffling at random",
                    "hint_fr": "Pas une stratégie de complétion.",
                    "hint_en": "Not a completion strategy.",
                },
            ],
        },
        {
            "structure_kind": "chain",
            "instruction_fr": "Complétez la chaîne logique cause → effet.",
            "instruction_en": "Complete the cause → effect logical chain.",
            "gaps": [
                {
                    "before": {"fr": "Cause initiale → ", "en": "Initial cause → "},
                    "after": {"fr": " → Propagation → Résultat", "en": " → Propagation → Outcome"},
                    "answer_fr": "Effet immédiat",
                    "answer_en": "Immediate effect",
                    "hint_fr": "Première conséquence observable.",
                    "hint_en": "First observable consequence.",
                },
                {
                    "before": {
                        "fr": "Sans cet effet, la propagation ",
                        "en": "Without this effect, propagation ",
                    },
                    "after": {"fr": ".", "en": "."},
                    "answer_fr": "ne peut pas démarrer",
                    "answer_en": "cannot start",
                    "hint_fr": "Lien de dépendance.",
                    "hint_en": "Dependency link.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "Résultat final anticipé",
                    "label_en": "Anticipated final outcome",
                    "hint_fr": "Trop tôt dans la chaîne.",
                    "hint_en": "Too early in the chain.",
                },
                {
                    "label_fr": "Cause inversée",
                    "label_en": "Reversed cause",
                    "hint_fr": "Inverse le sens causal.",
                    "hint_en": "Reverses the causal direction.",
                },
            ],
        },
        {
            "structure_kind": "formula",
            "instruction_fr": "Complétez la relation / formule conceptuelle.",
            "instruction_en": "Complete the conceptual relation / formula.",
            "gaps": [
                {
                    "before": {
                        "fr": f"{topic} = prérequis + ",
                        "en": f"{topic} = prerequisites + ",
                    },
                    "after": {"fr": " + vérification", "en": " + verification"},
                    "answer_fr": "application",
                    "answer_en": "application",
                    "hint_fr": "Étape centrale d'usage.",
                    "hint_en": "Central usage step.",
                },
                {
                    "before": {
                        "fr": "Si un élément manque, la relation devient ",
                        "en": "If an element is missing, the relation becomes ",
                    },
                    "after": {"fr": ".", "en": "."},
                    "answer_fr": "incomplète",
                    "answer_en": "incomplete",
                    "hint_fr": "État à restaurer.",
                    "hint_en": "State to restore.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "suppression",
                    "label_en": "deletion",
                    "hint_fr": "N'ajoute pas de cohérence.",
                    "hint_en": "Does not add coherence.",
                },
                {
                    "label_fr": "bruit",
                    "label_en": "noise",
                    "hint_fr": "Perturbe la structure.",
                    "hint_en": "Disrupts the structure.",
                },
            ],
        },
    ]


def build_transform_atelier_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi Atelier des transformations (forme → forme, invariant)."""
    from challenge_framework.question_intent import extract_focus_entity

    rng = random.Random(f"transform-atelier-{variant or label}-{difficulty}")
    entity = extract_focus_entity(label, object_meta) or (label or "élément").strip()
    topic = entity[:80]
    feedback_mode = "learning" if difficulty <= 2 else "evaluation"
    mode = "chain" if difficulty >= 3 else "single"

    sets = _transform_atelier_sets(topic, label)
    chosen = rng.choice(sets)

    if mode == "single":
        correct = chosen["correct_single"]
        distractors = list(chosen.get("distractors") or [])
        tools_raw = [correct, *distractors[: max(2, min(4, 1 + difficulty))]]
        solution_ids = ["op0"]
        # Réattribuer les ids après shuffle conceptuel
        tools = []
        for index, tool in enumerate(tools_raw):
            tool_id = f"op{index}"
            tools.append(
                {
                    "id": tool_id,
                    "label_fr": tool["label_fr"],
                    "label_en": tool["label_en"],
                    "result_fr": tool.get("result_fr") or "",
                    "result_en": tool.get("result_en") or "",
                    "preserves_invariant": bool(tool.get("preserves_invariant")),
                    "hint_fr": tool.get("hint_fr") or "",
                    "hint_en": tool.get("hint_en") or "",
                }
            )
        # Identifier l'outil correct après construction (premier = correct avant shuffle ids).
        correct_id = "op0"
        rng.shuffle(tools)
        # Remapper solution vers l'id du tool qui a le label du correct.
        for tool in tools:
            if tool["label_fr"] == correct["label_fr"]:
                correct_id = tool["id"]
                break
        solution_ids = [correct_id]
    else:
        steps = list(chosen.get("chain_steps") or [chosen["correct_single"]])
        step_count = max(2, min(len(steps), 2 + (difficulty - 3)))
        steps = steps[:step_count]
        distractors = list(chosen.get("distractors") or [])
        tools = []
        solution_ids = []
        for index, step in enumerate(steps):
            tool_id = f"s{index}"
            tools.append(
                {
                    "id": tool_id,
                    "label_fr": step["label_fr"],
                    "label_en": step["label_en"],
                    "result_fr": step.get("result_fr") or "",
                    "result_en": step.get("result_en") or "",
                    "preserves_invariant": True,
                    "hint_fr": step.get("hint_fr") or "",
                    "hint_en": step.get("hint_en") or "",
                }
            )
            solution_ids.append(tool_id)
        for d_index, dist in enumerate(distractors[: max(1, difficulty - 1)]):
            tools.append(
                {
                    "id": f"d{d_index}",
                    "label_fr": dist["label_fr"],
                    "label_en": dist["label_en"],
                    "result_fr": dist.get("result_fr") or "",
                    "result_en": dist.get("result_en") or "",
                    "preserves_invariant": bool(dist.get("preserves_invariant", False)),
                    "hint_fr": dist.get("hint_fr") or "",
                    "hint_en": dist.get("hint_en") or "",
                }
            )
        rng.shuffle(tools)

    return {
        "mechanic": "transform_atelier",
        "operation": operation or "transformer",
        "feedback_mode": feedback_mode,
        "mode": mode,
        "source_fr": chosen["source_fr"],
        "source_en": chosen["source_en"],
        "target_form_fr": chosen["target_form_fr"],
        "target_form_en": chosen["target_form_en"],
        "invariant_fr": chosen.get("invariant_fr") or "sens / valeur essentielle",
        "invariant_en": chosen.get("invariant_en") or "essential meaning / value",
        "final_result_fr": chosen.get("final_result_fr") or "",
        "final_result_en": chosen.get("final_result_en") or "",
        "instruction_fr": chosen.get("instruction_fr")
        or "Appliquez la bonne transformation en préservant l'invariant.",
        "instruction_en": chosen.get("instruction_en")
        or "Apply the right transformation while preserving the invariant.",
        "tools": tools,
        "solution": {"tool_ids": solution_ids},
    }


def _transform_atelier_sets(topic: str, label: str) -> list[dict[str, Any]]:
    label_l = (label or "").lower()
    if "voix" in label_l or "passive" in label_l or "active" in label_l:
        return [
            {
                "source_fr": "Le chat chasse la souris.",
                "source_en": "The cat chases the mouse.",
                "target_form_fr": "voix passive",
                "target_form_en": "passive voice",
                "invariant_fr": "sens de la phrase",
                "invariant_en": "sentence meaning",
                "final_result_fr": "La souris est chassée par le chat.",
                "final_result_en": "The mouse is chased by the cat.",
                "instruction_fr": "Transformez la phrase à la voix passive sans changer le sens.",
                "instruction_en": "Transform the sentence into the passive voice without changing meaning.",
                "correct_single": {
                    "label_fr": "Mettre à la voix passive",
                    "label_en": "Put into passive voice",
                    "result_fr": "La souris est chassée par le chat.",
                    "result_en": "The mouse is chased by the cat.",
                    "preserves_invariant": True,
                    "hint_fr": "Sujet et objet s'inversent, le sens reste.",
                    "hint_en": "Subject and object swap; meaning stays.",
                },
                "chain_steps": [
                    {
                        "label_fr": "Identifier sujet et objet",
                        "label_en": "Identify subject and object",
                        "result_fr": "Sujet=chat, objet=souris — Le chat chasse la souris.",
                        "result_en": "Subject=cat, object=mouse — The cat chases the mouse.",
                        "hint_fr": "Repérer qui agit et qui subit.",
                        "hint_en": "Spot who acts and who is acted on.",
                    },
                    {
                        "label_fr": "Passer à la voix passive",
                        "label_en": "Switch to passive voice",
                        "result_fr": "La souris est chassée par le chat.",
                        "result_en": "The mouse is chased by the cat.",
                        "hint_fr": "Objet devient sujet grammatical.",
                        "hint_en": "Object becomes grammatical subject.",
                    },
                ],
                "distractors": [
                    {
                        "label_fr": "Mettre au pluriel",
                        "label_en": "Make plural",
                        "result_fr": "Les chats chassent les souris.",
                        "result_en": "The cats chase the mice.",
                        "preserves_invariant": False,
                        "hint_fr": "Change le nombre, pas la voix.",
                        "hint_en": "Changes number, not voice.",
                    },
                    {
                        "label_fr": "Résumer",
                        "label_en": "Summarize",
                        "result_fr": "Une chasse.",
                        "result_en": "A chase.",
                        "preserves_invariant": False,
                        "hint_fr": "Perd des informations essentielles.",
                        "hint_en": "Loses essential information.",
                    },
                    {
                        "label_fr": "Traduire en anglais",
                        "label_en": "Translate to English",
                        "result_fr": "The cat chases the mouse.",
                        "result_en": "The cat chases the mouse.",
                        "preserves_invariant": True,
                        "hint_fr": "Préserve le sens mais pas la forme cible.",
                        "hint_en": "Keeps meaning but not the target form.",
                    },
                ],
            }
        ]

    if re.search(r"\d|pourcent|percent|fraction|0[.,]\d", label_l):
        return [
            {
                "source_fr": "0,75",
                "source_en": "0.75",
                "target_form_fr": "pourcentage",
                "target_form_en": "percentage",
                "invariant_fr": "valeur numérique",
                "invariant_en": "numeric value",
                "final_result_fr": "75 %",
                "final_result_en": "75%",
                "instruction_fr": "Convertissez la valeur en pourcentage sans changer la grandeur.",
                "instruction_en": "Convert the value to a percentage without changing the magnitude.",
                "correct_single": {
                    "label_fr": "Convertir en pourcentage",
                    "label_en": "Convert to percentage",
                    "result_fr": "75 %",
                    "result_en": "75%",
                    "preserves_invariant": True,
                    "hint_fr": "Multiplier par 100.",
                    "hint_en": "Multiply by 100.",
                },
                "chain_steps": [
                    {
                        "label_fr": "Écrire en fraction",
                        "label_en": "Write as a fraction",
                        "result_fr": "75/100",
                        "result_en": "75/100",
                        "hint_fr": "Forme fractionnaire équivalente.",
                        "hint_en": "Equivalent fractional form.",
                    },
                    {
                        "label_fr": "Simplifier",
                        "label_en": "Simplify",
                        "result_fr": "3/4",
                        "result_en": "3/4",
                        "hint_fr": "Même valeur, forme réduite.",
                        "hint_en": "Same value, reduced form.",
                    },
                    {
                        "label_fr": "Convertir en pourcentage",
                        "label_en": "Convert to percentage",
                        "result_fr": "75 %",
                        "result_en": "75%",
                        "hint_fr": "Forme cible atteinte.",
                        "hint_en": "Target form reached.",
                    },
                ],
                "distractors": [
                    {
                        "label_fr": "Arrondir à l'entier",
                        "label_en": "Round to integer",
                        "result_fr": "1",
                        "result_en": "1",
                        "preserves_invariant": False,
                        "hint_fr": "Perd la précision de la valeur.",
                        "hint_en": "Loses value precision.",
                    },
                    {
                        "label_fr": "Inverser",
                        "label_en": "Invert",
                        "result_fr": "1,333…",
                        "result_en": "1.333…",
                        "preserves_invariant": False,
                        "hint_fr": "Change la grandeur.",
                        "hint_en": "Changes the magnitude.",
                    },
                ],
            }
        ]

    return [
        {
            "source_fr": f"Schéma conceptuel de « {topic} »",
            "source_en": f"Concept map of “{topic}”",
            "target_form_fr": "texte explicatif court",
            "target_form_en": "short explanatory text",
            "invariant_fr": "contenu informationnel",
            "invariant_en": "informational content",
            "final_result_fr": f"{topic} repose sur des éléments liés qui forment un ensemble cohérent.",
            "final_result_en": f"{topic} relies on linked elements that form a coherent whole.",
            "instruction_fr": f"Transformez la représentation de « {topic} » en texte sans perdre l'essentiel.",
            "instruction_en": f"Transform the representation of “{topic}” into text without losing the essentials.",
            "correct_single": {
                "label_fr": "Reformuler en texte explicatif",
                "label_en": "Reformulate as explanatory text",
                "result_fr": f"{topic} repose sur des éléments liés qui forment un ensemble cohérent.",
                "result_en": f"{topic} relies on linked elements that form a coherent whole.",
                "preserves_invariant": True,
                "hint_fr": "Même contenu, autre forme.",
                "hint_en": "Same content, different form.",
            },
            "chain_steps": [
                {
                    "label_fr": "Extraire les concepts clés",
                    "label_en": "Extract key concepts",
                    "result_fr": f"Concepts : {topic}, relations, cohérence.",
                    "result_en": f"Concepts: {topic}, relations, coherence.",
                    "hint_fr": "Lister sans encore rédiger.",
                    "hint_en": "List without writing yet.",
                },
                {
                    "label_fr": "Rédiger le texte équivalent",
                    "label_en": "Write the equivalent text",
                    "result_fr": f"{topic} repose sur des éléments liés qui forment un ensemble cohérent.",
                    "result_en": f"{topic} relies on linked elements that form a coherent whole.",
                    "hint_fr": "Assembler en prose.",
                    "hint_en": "Assemble into prose.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "Supprimer les relations",
                    "label_en": "Remove the relations",
                    "result_fr": f"Liste isolée : {topic}.",
                    "result_en": f"Isolated list: {topic}.",
                    "preserves_invariant": False,
                    "hint_fr": "Perd la structure relationnelle.",
                    "hint_en": "Loses relational structure.",
                },
                {
                    "label_fr": "Résumer en un mot",
                    "label_en": "Summarize in one word",
                    "result_fr": topic.split()[0] if topic else "…",
                    "result_en": topic.split()[0] if topic else "…",
                    "preserves_invariant": False,
                    "hint_fr": "Trop d'information perdue.",
                    "hint_en": "Too much information lost.",
                },
                {
                    "label_fr": "Changer de sujet",
                    "label_en": "Change the topic",
                    "result_fr": "Un autre thème sans lien.",
                    "result_en": "Another unrelated theme.",
                    "preserves_invariant": False,
                    "hint_fr": "Invariant rompu.",
                    "hint_en": "Invariant broken.",
                },
            ],
        },
        {
            "source_fr": f"Formule descriptive de {topic}",
            "source_en": f"Descriptive formula for {topic}",
            "target_form_fr": "forme équivalente simplifiée",
            "target_form_en": "simplified equivalent form",
            "invariant_fr": "valeur / relation",
            "invariant_en": "value / relation",
            "final_result_fr": f"Forme équivalente de {topic}",
            "final_result_en": f"Equivalent form of {topic}",
            "instruction_fr": f"Réécrivez « {topic} » sous une forme équivalente.",
            "instruction_en": f"Rewrite “{topic}” in an equivalent form.",
            "correct_single": {
                "label_fr": "Réécrire sous forme équivalente",
                "label_en": "Rewrite in equivalent form",
                "result_fr": f"Forme équivalente de {topic}",
                "result_en": f"Equivalent form of {topic}",
                "preserves_invariant": True,
                "hint_fr": "Même relation, autre écriture.",
                "hint_en": "Same relation, different writing.",
            },
            "chain_steps": [
                {
                    "label_fr": "Développer",
                    "label_en": "Expand",
                    "result_fr": f"Forme développée de {topic}",
                    "result_en": f"Expanded form of {topic}",
                    "hint_fr": "Rendre explicite.",
                    "hint_en": "Make it explicit.",
                },
                {
                    "label_fr": "Simplifier",
                    "label_en": "Simplify",
                    "result_fr": f"Forme équivalente de {topic}",
                    "result_en": f"Equivalent form of {topic}",
                    "hint_fr": "Réduire sans perdre l'égalité.",
                    "hint_en": "Reduce without losing equality.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "Inverser les termes",
                    "label_en": "Invert the terms",
                    "result_fr": f"Inverse incorrect de {topic}",
                    "result_en": f"Incorrect inverse of {topic}",
                    "preserves_invariant": False,
                    "hint_fr": "Peut casser l'égalité.",
                    "hint_en": "May break equality.",
                },
                {
                    "label_fr": "Ajouter une constante arbitraire",
                    "label_en": "Add an arbitrary constant",
                    "result_fr": f"{topic} + C",
                    "result_en": f"{topic} + C",
                    "preserves_invariant": False,
                    "hint_fr": "Change la valeur.",
                    "hint_en": "Changes the value.",
                },
            ],
        },
    ]


def build_knowledge_bridges_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi Ponts du savoir (associations source → cible)."""
    from challenge_framework.question_intent import extract_focus_entity

    rng = random.Random(f"knowledge-bridges-{variant or label}-{difficulty}")
    entity = extract_focus_entity(label, object_meta) or (label or "éléments").strip()
    topic = entity[:80]
    feedback_mode = "learning" if difficulty <= 2 else "evaluation"

    pairs = _knowledge_bridges_pair_sets(topic, label)
    pair_set = rng.choice(pairs)
    selected = list(pair_set["pairs"])
    rng.shuffle(selected)
    selected = selected[: max(3, min(len(selected), 3 + difficulty))]

    sources = []
    targets = []
    solution: dict[str, str] = {}
    for index, pair in enumerate(selected):
        source_id = f"s{index}"
        target_id = f"t{index}"
        sources.append(
            {
                "id": source_id,
                "label_fr": pair["source_fr"],
                "label_en": pair["source_en"],
                "hint_fr": pair.get("hint_fr") or "",
                "hint_en": pair.get("hint_en") or "",
            }
        )
        targets.append(
            {
                "id": target_id,
                "label_fr": pair["target_fr"],
                "label_en": pair["target_en"],
            }
        )
        solution[source_id] = target_id

    # Distracteurs (cibles inutiles) à difficulté ≥ 3.
    if difficulty >= 3 and pair_set.get("distractors"):
        for d_index, distractor in enumerate(pair_set["distractors"]):
            targets.append(
                {
                    "id": f"d{d_index}",
                    "label_fr": distractor["label_fr"],
                    "label_en": distractor["label_en"],
                }
            )

    rng.shuffle(sources)
    rng.shuffle(targets)

    instruction_fr = pair_set.get("instruction_fr") or (
        "Relie chaque élément de gauche à l'élément correspondant à droite."
    )
    instruction_en = pair_set.get("instruction_en") or (
        "Link each left-hand item to the matching item on the right."
    )

    return {
        "mechanic": "knowledge_bridges",
        "operation": operation or "associer",
        "feedback_mode": feedback_mode,
        "exclusive_targets": True,
        "instruction_fr": instruction_fr,
        "instruction_en": instruction_en,
        "relation_fr": pair_set.get("relation_fr") or "",
        "relation_en": pair_set.get("relation_en") or "",
        "sources": sources,
        "targets": targets,
        "solution": solution,
    }


def _knowledge_bridges_pair_sets(topic: str, label: str) -> list[dict[str, Any]]:
    label_l = (label or "").lower()
    if re.search(r"\.(py|js|ts|html)\b", label_l) or "django" in label_l or "fichier" in label_l:
        return [
            {
                "instruction_fr": "Associez chaque fichier à son rôle principal.",
                "instruction_en": "Associate each file with its main role.",
                "relation_fr": "fichier → rôle",
                "relation_en": "file → role",
                "pairs": [
                    {
                        "source_fr": "models.py",
                        "source_en": "models.py",
                        "target_fr": "Définit les données persistantes",
                        "target_en": "Defines persistent data",
                        "hint_fr": "Structure des objets stockés en base.",
                        "hint_en": "Structure of objects stored in the database.",
                    },
                    {
                        "source_fr": "views.py",
                        "source_en": "views.py",
                        "target_fr": "Traite les requêtes HTTP",
                        "target_en": "Handles HTTP requests",
                        "hint_fr": "Point d'entrée des actions utilisateur.",
                        "hint_en": "Entry point for user actions.",
                    },
                    {
                        "source_fr": "urls.py",
                        "source_en": "urls.py",
                        "target_fr": "Route les URLs vers les vues",
                        "target_en": "Routes URLs to views",
                        "hint_fr": "Associe un chemin à une vue.",
                        "hint_en": "Maps a path to a view.",
                    },
                    {
                        "source_fr": "settings.py",
                        "source_en": "settings.py",
                        "target_fr": "Configure le projet",
                        "target_en": "Configures the project",
                        "hint_fr": "Paramètres globaux de l'application.",
                        "hint_en": "Global application settings.",
                    },
                    {
                        "source_fr": "serializers.py",
                        "source_en": "serializers.py",
                        "target_fr": "Transforme les données pour l'API",
                        "target_en": "Transforms data for the API",
                        "hint_fr": "Conversion entre modèles et JSON.",
                        "hint_en": "Conversion between models and JSON.",
                    },
                ],
                "distractors": [
                    {
                        "label_fr": "Compile le code source",
                        "label_en": "Compiles the source code",
                    },
                    {
                        "label_fr": "Gère le style CSS",
                        "label_en": "Manages CSS styles",
                    },
                ],
            }
        ]

    return [
        {
            "instruction_fr": f"Associez chaque notion liée à « {topic} » à sa description.",
            "instruction_en": f"Associate each notion related to “{topic}” with its description.",
            "relation_fr": "concept → description",
            "relation_en": "concept → description",
            "pairs": [
                {
                    "source_fr": f"Définition de {topic}",
                    "source_en": f"Definition of {topic}",
                    "target_fr": "Ce qu'est l'élément",
                    "target_en": "What the element is",
                    "hint_fr": "Caractérise l'identité du concept.",
                    "hint_en": "Characterizes the concept's identity.",
                },
                {
                    "source_fr": f"Rôle de {topic}",
                    "source_en": f"Role of {topic}",
                    "target_fr": "À quoi il sert",
                    "target_en": "What it is used for",
                    "hint_fr": "Fonction dans le système.",
                    "hint_en": "Function in the system.",
                },
                {
                    "source_fr": f"Exemple de {topic}",
                    "source_en": f"Example of {topic}",
                    "target_fr": "Occurrence concrète",
                    "target_en": "Concrete occurrence",
                    "hint_fr": "Cas particulier observable.",
                    "hint_en": "Observable particular case.",
                },
                {
                    "source_fr": f"Limite de {topic}",
                    "source_en": f"Limit of {topic}",
                    "target_fr": "Ce qu'il ne couvre pas",
                    "target_en": "What it does not cover",
                    "hint_fr": "Frontière d'application.",
                    "hint_en": "Boundary of application.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "Couleur préférée de l'équipe",
                    "label_en": "Team's favourite colour",
                }
            ],
        },
        {
            "instruction_fr": "Associez chaque cause à son effet probable.",
            "instruction_en": "Associate each cause with its likely effect.",
            "relation_fr": "cause → effet",
            "relation_en": "cause → effect",
            "pairs": [
                {
                    "source_fr": "Absence de validation",
                    "source_en": "Missing validation",
                    "target_fr": "Données incorrectes acceptées",
                    "target_en": "Incorrect data accepted",
                    "hint_fr": "Rien ne filtre les entrées.",
                    "hint_en": "Nothing filters the inputs.",
                },
                {
                    "source_fr": "Cache non invalidé",
                    "source_en": "Cache not invalidated",
                    "target_fr": "Affichage obsolète",
                    "target_en": "Stale display",
                    "hint_fr": "L'ancienne version reste servie.",
                    "hint_en": "The old version keeps being served.",
                },
                {
                    "source_fr": "Index manquant",
                    "source_en": "Missing index",
                    "target_fr": "Requêtes plus lentes",
                    "target_en": "Slower queries",
                    "hint_fr": "La base parcourt trop de lignes.",
                    "hint_en": "The database scans too many rows.",
                },
                {
                    "source_fr": "Secret exposé",
                    "source_en": "Exposed secret",
                    "target_fr": "Risque d'accès non autorisé",
                    "target_en": "Unauthorized access risk",
                    "hint_fr": "Un tiers peut s'authentifier.",
                    "hint_en": "A third party can authenticate.",
                },
            ],
            "distractors": [
                {
                    "label_fr": "Amélioration automatique de l'UX",
                    "label_en": "Automatic UX improvement",
                }
            ],
        },
    ]


def build_sorting_lab_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi Laboratoire de tri (classement par catégories)."""
    from challenge_framework.question_intent import extract_focus_entity

    rng = random.Random(f"sorting-lab-{variant or label}-{difficulty}")
    entity = extract_focus_entity(label, object_meta) or (label or "éléments").strip()
    topic = entity[:80]
    mode = "hidden" if difficulty >= 3 else "visible"
    feedback_mode = "learning" if difficulty <= 2 else "strict"

    # Jeux de catégories contextualisés (fichiers / concepts / générique).
    bundles = _sorting_lab_bundles(topic, label)
    bundle = rng.choice(bundles)

    categories = []
    items = []
    solution: dict[str, str] = {}
    for cat_index, cat in enumerate(bundle["categories"]):
        cat_id = f"c{cat_index}"
        categories.append(
            {
                "id": cat_id,
                "label_fr": cat["label_fr"],
                "label_en": cat["label_en"],
                "hidden_label_fr": f"Groupe {cat_index + 1}",
                "hidden_label_en": f"Group {cat_index + 1}",
            }
        )
        for item_index, item in enumerate(cat["items"]):
            item_id = f"i{cat_index}_{item_index}"
            items.append(
                {
                    "id": item_id,
                    "label_fr": item["label_fr"],
                    "label_en": item["label_en"],
                    "hint_fr": item.get("hint_fr") or "",
                    "hint_en": item.get("hint_en") or "",
                }
            )
            solution[item_id] = cat_id

    rng.shuffle(items)
    # Distracteur optionnel (élément ambigu) à difficulté ≥ 3.
    if difficulty >= 3 and bundle.get("trap"):
        trap = bundle["trap"]
        trap_id = "trap0"
        items.append(
            {
                "id": trap_id,
                "label_fr": trap["label_fr"],
                "label_en": trap["label_en"],
                "hint_fr": trap.get("hint_fr") or "",
                "hint_en": trap.get("hint_en") or "",
            }
        )
        solution[trap_id] = trap["category_id"]
        rng.shuffle(items)

    instruction_fr = (
        "Classez chaque élément dans la bonne catégorie. "
        + (
            "Les noms des groupes sont cachés : découvrez la règle de regroupement."
            if mode == "hidden"
            else "Appliquez la règle de classement indiquée par les étiquettes."
        )
    )
    instruction_en = (
        "Assign each item to the correct category. "
        + (
            "Group names are hidden: discover the grouping rule."
            if mode == "hidden"
            else "Apply the classification rule shown by the labels."
        )
    )

    return {
        "mechanic": "sorting_lab",
        "operation": operation or "classer",
        "mode": mode,
        "feedback_mode": feedback_mode,
        "instruction_fr": instruction_fr,
        "instruction_en": instruction_en,
        "items": items,
        "categories": categories,
        "solution": solution,
        "rule_fr": bundle.get("rule_fr") or "",
        "rule_en": bundle.get("rule_en") or "",
    }


def _sorting_lab_bundles(topic: str, label: str) -> list[dict[str, Any]]:
    label_l = (label or "").lower()
    if re.search(r"\.(py|js|ts|html)\b", label_l) or "django" in label_l or "fichier" in label_l:
        return [
            {
                "rule_fr": "Séparez les fichiers selon leur rôle dans l'application.",
                "rule_en": "Separate files by their role in the application.",
                "categories": [
                    {
                        "label_fr": "Données / modèles",
                        "label_en": "Data / models",
                        "items": [
                            {
                                "label_fr": "models.py",
                                "label_en": "models.py",
                                "hint_fr": "Définit la structure des données persistantes.",
                                "hint_en": "Defines persistent data structure.",
                            },
                            {
                                "label_fr": "serializers.py",
                                "label_en": "serializers.py",
                                "hint_fr": "Transforme les données pour l'API.",
                                "hint_en": "Transforms data for the API.",
                            },
                        ],
                    },
                    {
                        "label_fr": "Contrôle / requêtes",
                        "label_en": "Control / requests",
                        "items": [
                            {
                                "label_fr": "views.py",
                                "label_en": "views.py",
                                "hint_fr": "Traite les requêtes HTTP entrantes.",
                                "hint_en": "Handles incoming HTTP requests.",
                            },
                            {
                                "label_fr": "urls.py",
                                "label_en": "urls.py",
                                "hint_fr": "Route les URLs vers les vues.",
                                "hint_en": "Routes URLs to views.",
                            },
                        ],
                    },
                    {
                        "label_fr": "Configuration",
                        "label_en": "Configuration",
                        "items": [
                            {
                                "label_fr": "settings.py",
                                "label_en": "settings.py",
                                "hint_fr": "Paramètres globaux du projet.",
                                "hint_en": "Global project settings.",
                            },
                            {
                                "label_fr": "apps.py",
                                "label_en": "apps.py",
                                "hint_fr": "Configuration d'une application Django.",
                                "hint_en": "Django app configuration.",
                            },
                        ],
                    },
                ],
                "trap": {
                    "label_fr": "admin.py",
                    "label_en": "admin.py",
                    "category_id": "c1",
                    "hint_fr": "Expose les modèles dans l'interface d'administration.",
                    "hint_en": "Exposes models in the admin interface.",
                },
            }
        ]

    return [
        {
            "rule_fr": f"Regroupez les éléments liés à « {topic} » selon leur nature.",
            "rule_en": f"Group items related to “{topic}” by their nature.",
            "categories": [
                {
                    "label_fr": "Concepts",
                    "label_en": "Concepts",
                    "items": [
                        {
                            "label_fr": f"Notion centrale de {topic}",
                            "label_en": f"Core notion of {topic}",
                            "hint_fr": "Idée abstraite structurante.",
                            "hint_en": "Structuring abstract idea.",
                        },
                        {
                            "label_fr": f"Principe de {topic}",
                            "label_en": f"Principle of {topic}",
                            "hint_fr": "Règle générale du domaine.",
                            "hint_en": "General domain rule.",
                        },
                    ],
                },
                {
                    "label_fr": "Exemples concrets",
                    "label_en": "Concrete examples",
                    "items": [
                        {
                            "label_fr": f"Cas d'usage de {topic}",
                            "label_en": f"Use case of {topic}",
                            "hint_fr": "Situation observable d'application.",
                            "hint_en": "Observable application situation.",
                        },
                        {
                            "label_fr": f"Instance de {topic}",
                            "label_en": f"Instance of {topic}",
                            "hint_fr": "Occurrence particulière.",
                            "hint_en": "Particular occurrence.",
                        },
                    ],
                },
                {
                    "label_fr": "Procédures",
                    "label_en": "Procedures",
                    "items": [
                        {
                            "label_fr": f"Étape pour utiliser {topic}",
                            "label_en": f"Step to use {topic}",
                            "hint_fr": "Action ordonnée à réaliser.",
                            "hint_en": "Ordered action to perform.",
                        },
                        {
                            "label_fr": f"Méthode liée à {topic}",
                            "label_en": f"Method related to {topic}",
                            "hint_fr": "Façon de procéder.",
                            "hint_en": "Way of proceeding.",
                        },
                    ],
                },
            ],
        },
        {
            "rule_fr": "Classez selon le niveau d'abstraction.",
            "rule_en": "Classify by abstraction level.",
            "categories": [
                {
                    "label_fr": "Observables",
                    "label_en": "Observables",
                    "items": [
                        {
                            "label_fr": "Fait mesurable",
                            "label_en": "Measurable fact",
                            "hint_fr": "Donnée directement perceptible.",
                            "hint_en": "Directly perceptible data.",
                        },
                        {
                            "label_fr": "Exemple concret",
                            "label_en": "Concrete example",
                            "hint_fr": "Cas particulier visible.",
                            "hint_en": "Visible particular case.",
                        },
                    ],
                },
                {
                    "label_fr": "Relations",
                    "label_en": "Relations",
                    "items": [
                        {
                            "label_fr": "Lien cause-effet",
                            "label_en": "Cause-effect link",
                            "hint_fr": "Relie deux phénomènes.",
                            "hint_en": "Connects two phenomena.",
                        },
                        {
                            "label_fr": "Corrélation",
                            "label_en": "Correlation",
                            "hint_fr": "Association entre variables.",
                            "hint_en": "Association between variables.",
                        },
                    ],
                },
                {
                    "label_fr": "Modèles",
                    "label_en": "Models",
                    "items": [
                        {
                            "label_fr": "Schéma abstrait",
                            "label_en": "Abstract schema",
                            "hint_fr": "Représentation généralisante.",
                            "hint_en": "Generalizing representation.",
                        },
                        {
                            "label_fr": "Cadre théorique",
                            "label_en": "Theoretical frame",
                            "hint_fr": "Grille d'interprétation globale.",
                            "hint_en": "Global interpretation grid.",
                        },
                    ],
                },
            ],
        },
    ]


def build_comparator_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    """Construit un défi Comparateur expert (comparaison structurée critère par critère)."""
    from challenge_framework.question_intent import (
        extract_comparison_pair,
        extract_focus_entity,
    )

    pair = extract_comparison_pair(label, object_meta)
    if pair:
        left_name, right_name = pair
    else:
        entity = extract_focus_entity(label, object_meta) or (label or "concept").strip()
        left_name = f"{entity[:60]} (A)"
        right_name = f"{entity[:60]} (B)"

    rng = random.Random(f"comparator-{variant or label}-{difficulty}")
    is_file_pair = bool(
        re.search(r"\.\w+$", left_name) and re.search(r"\.\w+$", right_name)
    )
    context_hint = ""
    ctx_match = re.search(
        r"(?i)\b(?:dans|in)\s+(?:une?\s+|an?\s+)?(.+?)(?:\?|$)",
        str(label or ""),
    )
    if ctx_match:
        context_hint = _clean_snippet(ctx_match.group(1))

    criteria_defs = (
        _comparator_file_criteria(left_name, right_name, context_hint)
        if is_file_pair
        else _comparator_generic_criteria(left_name, right_name, context_hint)
    )

    required = min(3 + max(0, difficulty - 1), len(criteria_defs))
    selected = criteria_defs[:]
    rng.shuffle(selected)
    selected = selected[:required]

    element_a = {
        "id": "a",
        "label_fr": left_name,
        "label_en": left_name,
        "traits": {},
    }
    element_b = {
        "id": "b",
        "label_fr": right_name,
        "label_en": right_name,
        "traits": {},
    }

    relations: dict[str, str] = {}
    justification_answers: dict[str, str] = {}
    public_criteria: list[dict[str, Any]] = []

    for criterion in selected:
        key = criterion["key"]
        relations[key] = criterion["relation"]
        element_a["traits"][key] = {
            "fr": criterion["trait_a_fr"],
            "en": criterion["trait_a_en"],
        }
        element_b["traits"][key] = {
            "fr": criterion["trait_b_fr"],
            "en": criterion["trait_b_en"],
        }
        options = [
            {
                "id": f"{key}_ok",
                "text_fr": criterion["justification_fr"],
                "text_en": criterion["justification_en"],
            },
            {
                "id": f"{key}_bad",
                "text_fr": criterion["distractor_fr"],
                "text_en": criterion["distractor_en"],
            },
            {
                "id": f"{key}_vague",
                "text_fr": criterion["vague_fr"],
                "text_en": criterion["vague_en"],
            },
        ]
        rng.shuffle(options)
        justification_answers[key] = f"{key}_ok"
        public_criteria.append(
            {
                "key": key,
                "label_fr": criterion["label_fr"],
                "label_en": criterion["label_en"],
                "justification_options": options,
            }
        )

    synthesis_options = [
        {
            "id": "s_ok",
            "text_fr": (
                f"{left_name} et {right_name} appartiennent au même contexte"
                + (f" ({context_hint})" if context_hint else "")
                + " mais assurent des responsabilités distinctes et complémentaires."
            ),
            "text_en": (
                f"{left_name} and {right_name} belong to the same context"
                + (f" ({context_hint})" if context_hint else "")
                + " but fulfill distinct, complementary responsibilities."
            ),
        },
        {
            "id": "s_none",
            "text_fr": f"{left_name} et {right_name} n'ont aucun point commun.",
            "text_en": f"{left_name} and {right_name} have nothing in common.",
        },
        {
            "id": "s_same",
            "text_fr": f"{left_name} et {right_name} sont strictement interchangeables.",
            "text_en": f"{left_name} and {right_name} are strictly interchangeable.",
        },
    ]
    rng.shuffle(synthesis_options)

    return {
        "mechanic": "comparator",
        "operation": operation or "comparer",
        "instruction_fr": (
            f"Comparez {left_name} et {right_name} critère par critère : "
            "choisissez la relation (similaires / différents / partiellement similaires), "
            "justifiez, construisez la matrice, puis choisissez la meilleure synthèse."
        ),
        "instruction_en": (
            f"Compare {left_name} and {right_name} criterion by criterion: "
            "choose the relation (similar / different / partially similar), "
            "justify, build the matrix, then pick the best synthesis."
        ),
        "elements": [element_a, element_b],
        "criteria": public_criteria,
        "synthesis_options": synthesis_options,
        "required_criteria_count": len(selected),
        # Réponses attendues uniquement (retirées de l'API joueur si include_solution=false).
        "solution": {
            "relations": relations,
            "justifications": justification_answers,
            "synthesis_id": "s_ok",
        },
    }


def _clean_snippet(raw: str) -> str:
    text = (raw or "").strip(" ?.!,;:")
    text = re.sub(r"\s+", " ", text)
    return text[:80]


def _comparator_file_criteria(
    left_name: str, right_name: str, context_hint: str
) -> list[dict[str, str]]:
    ctx = context_hint or "cette application"
    return [
        {
            "key": "role",
            "label_fr": "Rôle / responsabilité",
            "label_en": "Role / responsibility",
            "relation": "different",
            "trait_a_fr": f"{left_name} définit surtout la structure des données et les règles métier associées.",
            "trait_a_en": f"{left_name} mainly defines data structure and related business rules.",
            "trait_b_fr": f"{right_name} orchestre surtout le traitement des requêtes et la réponse HTTP.",
            "trait_b_en": f"{right_name} mainly orchestrates request handling and the HTTP response.",
            "justification_fr": (
                f"{left_name} se concentre sur le modèle de données, alors que {right_name} "
                f"gère le flux requête/réponse dans {ctx}."
            ),
            "justification_en": (
                f"{left_name} focuses on the data model, whereas {right_name} "
                f"handles the request/response flow in {ctx}."
            ),
            "distractor_fr": f"{left_name} et {right_name} ont exactement le même rôle dans {ctx}.",
            "distractor_en": f"{left_name} and {right_name} have exactly the same role in {ctx}.",
            "vague_fr": f"{left_name} et {right_name} sont simplement différents.",
            "vague_en": f"{left_name} and {right_name} are simply different.",
        },
        {
            "key": "layer",
            "label_fr": "Couche applicative",
            "label_en": "Application layer",
            "relation": "different",
            "trait_a_fr": f"{left_name} appartient plutôt à la couche données / domaine.",
            "trait_a_en": f"{left_name} belongs more to the data / domain layer.",
            "trait_b_fr": f"{right_name} appartient plutôt à la couche présentation / contrôle.",
            "trait_b_en": f"{right_name} belongs more to the presentation / control layer.",
            "justification_fr": (
                f"Contrairement à {left_name} (couche données), {right_name} se situe "
                "côté contrôle/présentation."
            ),
            "justification_en": (
                f"Unlike {left_name} (data layer), {right_name} sits on the "
                "control/presentation side."
            ),
            "distractor_fr": f"{left_name} et {right_name} appartiennent à la même couche technique.",
            "distractor_en": f"{left_name} and {right_name} belong to the same technical layer.",
            "vague_fr": f"Les deux fichiers de {ctx} sont au même niveau d'abstraction.",
            "vague_en": f"Both files in {ctx} are at the same abstraction level.",
        },
        {
            "key": "lifecycle",
            "label_fr": "Moment d'utilisation",
            "label_en": "When it is used",
            "relation": "partial",
            "trait_a_fr": f"{left_name} est sollicité pour lire/écrire l'état persistant.",
            "trait_a_en": f"{left_name} is used to read/write persistent state.",
            "trait_b_fr": f"{right_name} est sollicité à chaque requête utilisateur entrante.",
            "trait_b_en": f"{right_name} is invoked on each incoming user request.",
            "justification_fr": (
                f"Les deux interviennent dans le traitement, mais {right_name} est le "
                f"point d'entrée HTTP tandis que {left_name} intervient pour persister ou charger les données."
            ),
            "justification_en": (
                f"Both take part in processing, but {right_name} is the HTTP entry point "
                f"while {left_name} is used to persist or load data."
            ),
            "distractor_fr": f"{left_name} et {right_name} sont appelés exactement au même moment.",
            "distractor_en": f"{left_name} and {right_name} are called at exactly the same moment.",
            "vague_fr": f"Les deux fichiers sont utilisés de la même façon dans {ctx}.",
            "vague_en": f"Both files are used the same way in {ctx}.",
        },
        {
            "key": "dependency",
            "label_fr": "Dépendances typiques",
            "label_en": "Typical dependencies",
            "relation": "different",
            "trait_a_fr": f"{left_name} dépend surtout de l'ORM / du schéma de base.",
            "trait_a_en": f"{left_name} mostly depends on the ORM / database schema.",
            "trait_b_fr": f"{right_name} dépend des modèles, formulaires/serializers et du routage.",
            "trait_b_en": f"{right_name} depends on models, forms/serializers, and routing.",
            "justification_fr": (
                f"{right_name} s'appuie souvent sur {left_name}, alors que {left_name} "
                "ne dépend en principe pas des vues."
            ),
            "justification_en": (
                f"{right_name} often relies on {left_name}, whereas {left_name} "
                "typically does not depend on views."
            ),
            "distractor_fr": f"{left_name} dépend des vues et {right_name} dépend de la base uniquement.",
            "distractor_en": f"{left_name} depends on views and {right_name} depends only on the database.",
            "vague_fr": f"Les dépendances de {left_name} et {right_name} sont identiques.",
            "vague_en": f"Dependencies of {left_name} and {right_name} are identical.",
        },
    ]


def _comparator_generic_criteria(
    left_name: str, right_name: str, context_hint: str
) -> list[dict[str, str]]:
    ctx = context_hint or "ce domaine"
    return [
        {
            "key": "purpose",
            "label_fr": "Finalité",
            "label_en": "Purpose",
            "relation": "different",
            "trait_a_fr": f"{left_name} vise un objectif distinct dans {ctx}.",
            "trait_a_en": f"{left_name} targets a distinct goal in {ctx}.",
            "trait_b_fr": f"{right_name} vise un autre objectif complémentaire dans {ctx}.",
            "trait_b_en": f"{right_name} targets another complementary goal in {ctx}.",
            "justification_fr": (
                f"{left_name} et {right_name} n'ont pas la même finalité, "
                f"même s'ils peuvent coexister dans {ctx}."
            ),
            "justification_en": (
                f"{left_name} and {right_name} do not share the same purpose, "
                f"even though they may coexist in {ctx}."
            ),
            "distractor_fr": f"{left_name} et {right_name} ont exactement la même finalité.",
            "distractor_en": f"{left_name} and {right_name} have exactly the same purpose.",
            "vague_fr": f"{left_name} et {right_name} sont simplement différents.",
            "vague_en": f"{left_name} and {right_name} are simply different.",
        },
        {
            "key": "structure",
            "label_fr": "Structure",
            "label_en": "Structure",
            "relation": "partial",
            "trait_a_fr": f"La structure de {left_name} met en avant certains éléments clés.",
            "trait_a_en": f"The structure of {left_name} highlights certain key elements.",
            "trait_b_fr": f"La structure de {right_name} organise autrement ces éléments.",
            "trait_b_en": f"The structure of {right_name} organizes these elements differently.",
            "justification_fr": (
                f"Les deux partagent un cadre commun, mais {left_name} et {right_name} "
                "organisent leurs éléments de façon différente."
            ),
            "justification_en": (
                f"Both share a common frame, but {left_name} and {right_name} "
                "organize their elements differently."
            ),
            "distractor_fr": f"{left_name} et {right_name} ont une structure identique.",
            "distractor_en": f"{left_name} and {right_name} have an identical structure.",
            "vague_fr": f"La structure n'a pas d'importance pour comparer {left_name} et {right_name}.",
            "vague_en": f"Structure does not matter when comparing {left_name} and {right_name}.",
        },
        {
            "key": "usage",
            "label_fr": "Usage",
            "label_en": "Usage",
            "relation": "different",
            "trait_a_fr": f"{left_name} s'emploie dans un type de situation précis.",
            "trait_a_en": f"{left_name} is used in a specific kind of situation.",
            "trait_b_fr": f"{right_name} s'emploie dans d'autres situations, souvent complémentaires.",
            "trait_b_en": f"{right_name} is used in other, often complementary situations.",
            "justification_fr": (
                f"On choisit {left_name} ou {right_name} selon le besoin : "
                "leurs usages typiques divergent."
            ),
            "justification_en": (
                f"One chooses {left_name} or {right_name} depending on the need: "
                "their typical usages diverge."
            ),
            "distractor_fr": f"{left_name} et {right_name} s'utilisent toujours de façon interchangeable.",
            "distractor_en": f"{left_name} and {right_name} are always used interchangeably.",
            "vague_fr": f"L'usage de {left_name} et {right_name} est indiscernable.",
            "vague_en": f"Usage of {left_name} and {right_name} is indistinguishable.",
        },
        {
            "key": "limits",
            "label_fr": "Limites",
            "label_en": "Limits",
            "relation": "partial",
            "trait_a_fr": f"{left_name} a des limites propres (périmètre, contraintes).",
            "trait_a_en": f"{left_name} has its own limits (scope, constraints).",
            "trait_b_fr": f"{right_name} présente d'autres limites, parfois opposées.",
            "trait_b_en": f"{right_name} has other limits, sometimes opposite ones.",
            "justification_fr": (
                f"Les deux ont des limites, mais pas les mêmes : "
                f"celles de {left_name} ne coïncident pas avec celles de {right_name}."
            ),
            "justification_en": (
                f"Both have limits, but not the same ones: "
                f"those of {left_name} do not match those of {right_name}."
            ),
            "distractor_fr": f"{left_name} et {right_name} ont exactement les mêmes limites.",
            "distractor_en": f"{left_name} and {right_name} have exactly the same limits.",
            "vague_fr": f"Aucune limite ne distingue {left_name} de {right_name}.",
            "vague_en": f"No limit distinguishes {left_name} from {right_name}.",
        },
    ]


def _append_investigation_statement(
    statements: list[dict[str, str]],
    solution: dict[str, bool],
    *,
    statement_id: str,
    text_fr: str,
    text_en: str,
    value: bool,
) -> None:
    statements.append(
        {
            "id": statement_id,
            "text_fr": text_fr[:240],
            "text_en": text_en[:240],
        }
    )
    solution[statement_id] = value


def build_investigation_content(
    *,
    label: str,
    object_meta: dict[str, Any],
    operation: str,
    difficulty: int,
    variant: str | None = None,
    lang: str | None = None,
    pair_candidates: list[tuple[str, str]] | None = None,
    source_exercise_id: int | None = None,
) -> dict[str, Any]:
    """Construit un défi enquête (affirmations Vrai/Faux)."""
    from challenge_framework.question_intent import extract_focus_entity

    entity = extract_focus_entity(label, object_meta)
    rng = random.Random(variant or label or str(source_exercise_id or 0))
    statements: list[dict[str, str]] = []
    solution: dict[str, bool] = {}
    idx = 0

    def add(text_fr: str, text_en: str, value: bool) -> None:
        nonlocal idx
        _append_investigation_statement(
            statements,
            solution,
            statement_id=f"s{idx}",
            text_fr=text_fr,
            text_en=text_en,
            value=value,
        )
        idx += 1

    role_statements = _role_investigation_statements(entity, label, object_meta)
    if role_statements:
        for text_fr, text_en, value in role_statements:
            add(text_fr, text_en, value)
    elif len(entity) < max(40, int(len(label) * 0.75)):
        add(
            f"« {entity} » remplit un rôle utile dans le contexte étudié.",
            f"\"{entity}\" plays a useful role in the studied context.",
            True,
        )
        add(
            f"« {entity} » n'a aucun rôle fonctionnel dans le contexte étudié.",
            f"\"{entity}\" has no functional role in the studied context.",
            False,
        )

    pairs = _filter_contextual_pairs(pair_candidates or [])
    if not pairs and not role_statements:
        items = _fallback_items_from_context(label, object_meta, operation, rng)
        contextual_items = [item for item in items if not _is_generic_challenge_token(item)]
        for item in contextual_items[: max(2, min(4, difficulty + 1))]:
            pairs.append((item, f"concept lié à {entity}"))

    selected_pairs = pairs[:]
    rng.shuffle(selected_pairs)
    selected_pairs = selected_pairs[: min(2, len(selected_pairs))]

    for i, (left, right) in enumerate(selected_pairs):
        add(
            f"Il est vrai que « {left} » correspond à : {right}.",
            f"It is true that \"{left}\" corresponds to: {right}.",
            True,
        )
        if len(selected_pairs) > 1:
            other = selected_pairs[(i + 1) % len(selected_pairs)]
            wrong_right = other[1] if other[1] != right else selected_pairs[(i + 2) % len(selected_pairs)][1]
            add(
                f"Il est vrai que « {left} » correspond à : {wrong_right}.",
                f"It is true that \"{left}\" corresponds to: {wrong_right}.",
                False,
            )

    if not statements:
        add(
            f"« {entity} » est pertinent pour répondre à la question étudiée.",
            f"\"{entity}\" is relevant to answering the studied question.",
            True,
        )
        add(
            f"« {entity} » n'est pas lié au sujet de la question.",
            f"\"{entity}\" is unrelated to the question topic.",
            False,
        )

    target_count = min(8, max(4, 3 + min(difficulty, 2)))
    if len(statements) > target_count:
        statements = statements[:target_count]
        solution = {entry["id"]: solution[entry["id"]] for entry in statements}

    rng.shuffle(statements)

    instruction_fr = _fallback_instruction_fr("investigation", operation, label)
    instruction_en = _fallback_instruction_en("investigation", operation, label)

    content: dict[str, Any] = {
        "mechanic": "investigation",
        "operation": operation,
        "instruction_fr": instruction_fr,
        "instruction_en": instruction_en,
        "statements": statements,
        "solution": solution,
        "focus_entity": entity,
        "generated_by": "investigation_reinforcement" if source_exercise_id else "rule_based",
    }
    if source_exercise_id is not None:
        content["source_exercise_id"] = source_exercise_id
    return content


def can_build_investigation_reinforcement(
    source_content: dict[str, Any],
    question_label: str = "",
) -> bool:
    if str(source_content.get("mechanic") or "") == "investigation":
        return False
    from challenge_framework.question_intent import is_explanation_question

    if is_explanation_question(question_label):
        return True
    return len(extract_memory_pair_candidates(source_content)) >= 2


def build_investigation_reinforcement_content(
    source_content: dict[str, Any],
    *,
    question_label: str,
    operation: str,
    source_exercise_id: int,
    lang: str | None = None,
    object_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Défi enquête secondaire pour renforcer la compréhension après un premier défi."""
    from challenge_framework.question_intent import is_explanation_question

    meta = object_meta or {}
    pairs = extract_memory_pair_candidates(source_content)
    if is_explanation_question(question_label):
        pairs = []
    if not can_build_investigation_reinforcement(source_content, question_label) and len(pairs) < 2:
        raise ValueError(
            "Impossible de créer un défi enquête : question non explicative et paires insuffisantes."
        )
    return build_investigation_content(
        label=question_label or "Concept étudié",
        object_meta=meta,
        operation=operation or "expliquer",
        difficulty=2,
        variant=f"investigation-{source_exercise_id}",
        lang=lang,
        pair_candidates=pairs,
        source_exercise_id=source_exercise_id,
    )


def evaluate_attempt(content: dict[str, Any], learner_actions: dict[str, Any]) -> dict[str, Any]:
    solution = content.get("solution")
    mechanic = content.get("mechanic", "")
    passed = False
    score = 0.0
    criteria: dict[str, Any] = {}

    if mechanic == "matching":
        answers = learner_actions.get("pairs") or {}
        expected = solution or {}
        if expected:
            correct = sum(1 for k, v in expected.items() if answers.get(k) == v)
            score = correct / len(expected)
            passed = score >= 0.8
            criteria = {"correct_pairs": correct, "total_pairs": len(expected)}
    elif mechanic == "sorting":
        answer = learner_actions.get("order") or []
        expected = solution or []
        if expected:
            correct_positions = sum(
                1 for i, v in enumerate(expected) if i < len(answer) and answer[i] == v
            )
            score = correct_positions / len(expected)
            passed = answer == expected
            criteria = {"correct_positions": correct_positions, "total": len(expected)}
    elif mechanic == "drag_drop":
        answers = learner_actions.get("placements") or {}
        expected = solution or {}
        if expected:
            correct = sum(1 for k, v in expected.items() if answers.get(k) == v)
            score = correct / len(expected)
            passed = score >= 0.75
            criteria = {"correct_placements": correct, "total": len(expected)}
    elif mechanic == "memory":
        expected = solution if isinstance(solution, dict) else {}
        matched_raw = learner_actions.get("matched_pair_ids") or []
        matched = {str(pair_id) for pair_id in matched_raw}
        expected_ids = {str(pair_id) for pair_id in expected}
        total = len(expected_ids)
        correct = len(matched & expected_ids)
        score = correct / total if total else 0.0
        passed = matched == expected_ids and total > 0
        moves = int(learner_actions.get("moves") or 0)
        criteria = {
            "matched_pairs": correct,
            "total_pairs": total,
            "moves": moves,
        }
    elif mechanic == "investigation":
        answers = learner_actions.get("answers") or {}
        expected = solution if isinstance(solution, dict) else {}
        bool_expected = {str(k): bool(v) for k, v in expected.items()}
        if bool_expected:
            correct = sum(
                1 for key, value in bool_expected.items() if answers.get(key) is value
            )
            score = correct / len(bool_expected)
            passed = score >= 0.8
            criteria = {"correct_answers": correct, "total_statements": len(bool_expected)}
    elif mechanic == "comparator":
        expected = solution if isinstance(solution, dict) else {}
        expected_relations = (
            expected.get("relations") if isinstance(expected.get("relations"), dict) else {}
        )
        expected_justifs = (
            expected.get("justifications")
            if isinstance(expected.get("justifications"), dict)
            else {}
        )
        expected_synth_id = str(
            expected.get("synthesis_id")
            or (
                (expected.get("synthesis") or {}).get("correct_id")
                if isinstance(expected.get("synthesis"), dict)
                else ""
            )
            or ""
        )

        learner_relations = learner_actions.get("relations") or {}
        learner_justifs = learner_actions.get("justifications") or {}
        learner_synth = str(learner_actions.get("synthesis_id") or "")

        relation_keys = list(expected_relations.keys())
        relation_correct = 0
        justif_correct = 0
        justif_total = 0
        per_criterion: dict[str, dict[str, bool]] = {}
        for key in relation_keys:
            relation_ok = str(learner_relations.get(key) or "") == str(
                expected_relations.get(key) or ""
            )
            if relation_ok:
                relation_correct += 1
            raw_expected = expected_justifs.get(key)
            if isinstance(raw_expected, dict):
                correct_id = str(raw_expected.get("correct_id") or "")
            else:
                correct_id = str(raw_expected or "")
            justification_ok = False
            if correct_id:
                justif_total += 1
                justification_ok = str(learner_justifs.get(key) or "") == correct_id
                if justification_ok:
                    justif_correct += 1
            per_criterion[str(key)] = {
                "relation_ok": relation_ok,
                "justification_ok": justification_ok if correct_id else True,
            }

        synth_ok = 1.0 if expected_synth_id and learner_synth == expected_synth_id else 0.0
        relation_score = relation_correct / len(relation_keys) if relation_keys else 0.0
        justif_score = justif_correct / justif_total if justif_total else 0.0
        score = 0.4 * relation_score + 0.3 * justif_score + 0.3 * synth_ok
        passed = score >= 0.75
        criteria = {
            "relation_correct": relation_correct,
            "relation_total": len(relation_keys),
            "justification_correct": justif_correct,
            "justification_total": justif_total,
            "synthesis_ok": bool(synth_ok),
            "per_criterion": per_criterion,
        }
    elif mechanic == "sorting_lab":
        expected = solution if isinstance(solution, dict) else {}
        placements = learner_actions.get("placements") or {}
        if not isinstance(placements, dict):
            placements = {}
        total = len(expected)
        correct = 0
        per_item: dict[str, dict[str, Any]] = {}
        items_by_id = {
            str(item.get("id")): item
            for item in (content.get("items") or [])
            if isinstance(item, dict) and item.get("id") is not None
        }
        for item_id, cat_id in expected.items():
            key = str(item_id)
            ok = str(placements.get(key) or placements.get(item_id) or "") == str(cat_id)
            if ok:
                correct += 1
            item = items_by_id.get(key) or {}
            per_item[key] = {
                "correct": ok,
                "expected_category_id": str(cat_id),
                "hint_fr": str(item.get("hint_fr") or "") if not ok else "",
                "hint_en": str(item.get("hint_en") or "") if not ok else "",
            }
        score = correct / total if total else 0.0
        passed = score >= 0.8
        incorrect_attempts = int(learner_actions.get("incorrect_attempts") or 0)
        moves = int(learner_actions.get("moves") or 0)
        criteria = {
            "correct_placements": correct,
            "total": total,
            "incorrect_attempts": incorrect_attempts,
            "moves": moves,
            "per_item": per_item,
            "mode": content.get("mode") or "visible",
            "feedback_mode": content.get("feedback_mode") or "strict",
        }
    elif mechanic == "knowledge_bridges":
        expected = solution if isinstance(solution, dict) else {}
        links = learner_actions.get("links") or {}
        if not isinstance(links, dict):
            links = {}
        total = len(expected)
        correct = 0
        per_link: dict[str, dict[str, Any]] = {}
        sources_by_id = {
            str(src.get("id")): src
            for src in (content.get("sources") or [])
            if isinstance(src, dict) and src.get("id") is not None
        }
        for source_id, target_id in expected.items():
            key = str(source_id)
            ok = str(links.get(key) or links.get(source_id) or "") == str(target_id)
            if ok:
                correct += 1
            source = sources_by_id.get(key) or {}
            per_link[key] = {
                "correct": ok,
                "expected_target_id": str(target_id),
                "hint_fr": str(source.get("hint_fr") or "") if not ok else "",
                "hint_en": str(source.get("hint_en") or "") if not ok else "",
            }
        score = correct / total if total else 0.0
        passed = score >= 0.8
        incorrect_attempts = int(learner_actions.get("incorrect_attempts") or 0)
        criteria = {
            "correct_links": correct,
            "total": total,
            "incorrect_attempts": incorrect_attempts,
            "per_link": per_link,
            "feedback_mode": content.get("feedback_mode") or "evaluation",
        }
    elif mechanic == "sequence_frieze":
        expected = solution if isinstance(solution, list) else []
        answer = learner_actions.get("order") or []
        if not isinstance(answer, list):
            answer = []
        total = len(expected)
        exact_correct = 0
        distance_sum = 0.0
        per_position: dict[str, dict[str, Any]] = {}
        answer_index = {str(v): i for i, v in enumerate(answer)}
        items_by_id = {
            str(item.get("id")): item
            for item in (content.get("items") or [])
            if isinstance(item, dict) and item.get("id") is not None
        }
        for i, expected_id in enumerate(expected):
            key = str(expected_id)
            actual_id = str(answer[i]) if i < len(answer) else ""
            ok = actual_id == key
            if ok:
                exact_correct += 1
            actual_pos = answer_index.get(key)
            if actual_pos is None:
                dist_score = 0.0
            else:
                dist_score = 1.0 - (abs(actual_pos - i) / max(total - 1, 1))
            distance_sum += dist_score
            item = items_by_id.get(key) or {}
            per_position[str(i)] = {
                "correct": ok,
                "expected_id": key,
                "actual_id": actual_id,
                "distance_score": round(dist_score, 3),
                "hint_fr": str(item.get("hint_fr") or "") if not ok else "",
                "hint_en": str(item.get("hint_en") or "") if not ok else "",
            }
        exact_score = exact_correct / total if total else 0.0
        distance_score = distance_sum / total if total else 0.0
        score = 0.7 * exact_score + 0.3 * distance_score
        passed = score >= 0.8
        criteria = {
            "correct_positions": exact_correct,
            "total": total,
            "exact_score": round(exact_score, 3),
            "distance_score": round(distance_score, 3),
            "per_position": per_position,
            "feedback_mode": content.get("feedback_mode") or "evaluation",
        }
    elif mechanic == "missing_fragment":
        expected = solution if isinstance(solution, dict) else {}
        placements = learner_actions.get("placements") or {}
        if not isinstance(placements, dict):
            placements = {}
        total = len(expected)
        correct = 0
        per_gap: dict[str, dict[str, Any]] = {}
        fragments_by_id = {
            str(frag.get("id")): frag
            for frag in (content.get("fragments") or [])
            if isinstance(frag, dict) and frag.get("id") is not None
        }
        for gap_id, frag_id in expected.items():
            key = str(gap_id)
            actual = str(placements.get(key) or placements.get(gap_id) or "")
            ok = actual == str(frag_id)
            if ok:
                correct += 1
            expected_frag = fragments_by_id.get(str(frag_id)) or {}
            per_gap[key] = {
                "correct": ok,
                "expected_fragment_id": str(frag_id),
                "actual_fragment_id": actual,
                "hint_fr": str(expected_frag.get("hint_fr") or "") if not ok else "",
                "hint_en": str(expected_frag.get("hint_en") or "") if not ok else "",
            }
        score = correct / total if total else 0.0
        passed = score >= 0.8
        incorrect_attempts = int(learner_actions.get("incorrect_attempts") or 0)
        criteria = {
            "correct_gaps": correct,
            "total": total,
            "incorrect_attempts": incorrect_attempts,
            "per_gap": per_gap,
            "feedback_mode": content.get("feedback_mode") or "evaluation",
        }
    elif mechanic == "transform_atelier":
        solution_obj = solution if isinstance(solution, dict) else {}
        expected_ids = [
            str(x) for x in (solution_obj.get("tool_ids") or []) if str(x).strip()
        ]
        selected = learner_actions.get("selected_tools") or []
        if not isinstance(selected, list):
            selected = []
        selected_ids = [str(x) for x in selected]
        total = len(expected_ids)
        prefix = 0
        for i, expected_id in enumerate(expected_ids):
            if i < len(selected_ids) and selected_ids[i] == expected_id:
                prefix += 1
            else:
                break
        exact = selected_ids == expected_ids
        sequence_score = 1.0 if exact else (prefix / total if total else 0.0)

        tools_by_id = {
            str(tool.get("id")): tool
            for tool in (content.get("tools") or [])
            if isinstance(tool, dict) and tool.get("id") is not None
        }
        preserved = 0
        for tid in selected_ids:
            tool = tools_by_id.get(tid) or {}
            if tool.get("preserves_invariant"):
                preserved += 1
        integrity = preserved / len(selected_ids) if selected_ids else 0.0
        # Si aucune sélection : intégrité nulle.
        score = 0.7 * sequence_score + 0.3 * integrity
        if exact:
            score = 1.0
            integrity = 1.0
        passed = score >= 0.8
        incorrect_attempts = int(learner_actions.get("incorrect_attempts") or 0)
        criteria = {
            "expected_tools": expected_ids,
            "selected_tools": selected_ids,
            "correct_prefix": prefix,
            "total": total,
            "sequence_score": round(sequence_score, 3),
            "integrity": round(integrity, 3),
            "incorrect_attempts": incorrect_attempts,
            "mode": content.get("mode") or "single",
            "feedback_mode": content.get("feedback_mode") or "evaluation",
        }
    else:
        answer = learner_actions.get("selected")
        expected = solution
        passed = answer == expected
        score = 1.0 if passed else 0.0
        criteria = {"selected": answer, "expected": expected}

    return {
        "score": round(score, 3),
        "passed": passed,
        "criteria_results": criteria,
        "feedback": {
            "fr": "Bravo !" if passed else "Continuez — analysez vos erreurs et réessayez.",
            "en": "Well done!" if passed else "Keep going — review your mistakes and try again.",
        },
    }


def check_sorting_lab_placement(
    content: dict[str, Any],
    *,
    item_id: str,
    category_id: str,
) -> dict[str, Any]:
    """Vérifie un placement unitaire (feedback immédiat, sans exposer toute la solution)."""
    solution = content.get("solution") if isinstance(content.get("solution"), dict) else {}
    expected = str(solution.get(item_id) or solution.get(str(item_id)) or "")
    correct = bool(expected) and expected == str(category_id)
    hint_fr = ""
    hint_en = ""
    if not correct:
        for item in content.get("items") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("id")) != str(item_id):
                continue
            hint_fr = str(item.get("hint_fr") or "")
            hint_en = str(item.get("hint_en") or "")
            break
    return {
        "correct": correct,
        "hint_fr": hint_fr,
        "hint_en": hint_en,
        "feedback_mode": content.get("feedback_mode") or "strict",
        "mode": content.get("mode") or "visible",
    }


def check_knowledge_bridges_link(
    content: dict[str, Any],
    *,
    source_id: str,
    target_id: str,
) -> dict[str, Any]:
    """Vérifie un lien unitaire (feedback immédiat en mode apprentissage)."""
    solution = content.get("solution") if isinstance(content.get("solution"), dict) else {}
    expected = str(solution.get(source_id) or solution.get(str(source_id)) or "")
    correct = bool(expected) and expected == str(target_id)
    hint_fr = ""
    hint_en = ""
    if not correct:
        for source in content.get("sources") or []:
            if not isinstance(source, dict):
                continue
            if str(source.get("id")) != str(source_id):
                continue
            hint_fr = str(source.get("hint_fr") or "")
            hint_en = str(source.get("hint_en") or "")
            break
    return {
        "correct": correct,
        "hint_fr": hint_fr,
        "hint_en": hint_en,
        "feedback_mode": content.get("feedback_mode") or "evaluation",
    }


def check_missing_fragment_placement(
    content: dict[str, Any],
    *,
    gap_id: str,
    fragment_id: str,
) -> dict[str, Any]:
    """Vérifie un placement unitaire (feedback immédiat en mode apprentissage)."""
    solution = content.get("solution") if isinstance(content.get("solution"), dict) else {}
    expected = str(solution.get(gap_id) or solution.get(str(gap_id)) or "")
    correct = bool(expected) and expected == str(fragment_id)
    hint_fr = ""
    hint_en = ""
    if not correct:
        for frag in content.get("fragments") or []:
            if not isinstance(frag, dict):
                continue
            if str(frag.get("id")) != str(expected):
                continue
            hint_fr = str(frag.get("hint_fr") or "")
            hint_en = str(frag.get("hint_en") or "")
            break
    return {
        "correct": correct,
        "hint_fr": hint_fr,
        "hint_en": hint_en,
        "feedback_mode": content.get("feedback_mode") or "evaluation",
    }


def check_transform_atelier_step(
    content: dict[str, Any],
    *,
    tool_id: str,
    step_index: int = 0,
) -> dict[str, Any]:
    """Vérifie une opération unitaire (feedback immédiat en mode apprentissage)."""
    solution = content.get("solution") if isinstance(content.get("solution"), dict) else {}
    expected_ids = [str(x) for x in (solution.get("tool_ids") or [])]
    expected = expected_ids[step_index] if 0 <= step_index < len(expected_ids) else ""
    correct = bool(expected) and expected == str(tool_id)
    tools_by_id = {
        str(tool.get("id")): tool
        for tool in (content.get("tools") or [])
        if isinstance(tool, dict) and tool.get("id") is not None
    }
    tool = tools_by_id.get(str(tool_id)) or {}
    expected_tool = tools_by_id.get(str(expected)) or {}
    hint_fr = ""
    hint_en = ""
    if not correct:
        hint_fr = str(expected_tool.get("hint_fr") or tool.get("hint_fr") or "")
        hint_en = str(expected_tool.get("hint_en") or tool.get("hint_en") or "")
    return {
        "correct": correct,
        "preserves_invariant": bool(tool.get("preserves_invariant")),
        "result_fr": str(tool.get("result_fr") or "") if correct else "",
        "result_en": str(tool.get("result_en") or "") if correct else "",
        "hint_fr": hint_fr,
        "hint_en": hint_en,
        "feedback_mode": content.get("feedback_mode") or "evaluation",
        "next_step_index": step_index + 1 if correct else step_index,
        "complete": correct and (step_index + 1) >= len(expected_ids),
    }
