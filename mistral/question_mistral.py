"""Génération IA d'exercices de défi cognitif (Mistral)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mistralai.client import Mistral

from .discovering_mistral import (
    MISTRAL_CHAT_TIMEOUT_MS,
    MISTRAL_DISCOVER_MAX_TOKENS,
    mistral_message_content_to_text,
    parse_json_object_from_llm_content,
)
from .language_prompts import prompt_prefix
from .pyramid_prompts import PYRAMID_CONSTITUTION, normalize_pyramid_level

MECHANIC_SCHEMAS: dict[str, str] = {
    "matching": """
{
  "mechanic": "matching",
  "operation": "<operation_key>",
  "instruction_fr": "...",
  "instruction_en": "...",
  "pairs": [{"left": "...", "right": "..."}],
  "solution": {"left_item": "right_item"}
}
Note : chaque réponse (right) doit être UNIQUE ; ne pas aligner l'ordre des paires avec l'ordre des bonnes réponses.
Interface joueur : pastilles cliquables (une réponse par ligne) — PAS de glisser-déposer.
Consignes : décrire l'association par CLIC ; interdit « glisser », « déposer », « droite/gauche ».
""",
    "sorting": """
{
  "mechanic": "sorting",
  "operation": "<operation_key>",
  "instruction_fr": "...",
  "instruction_en": "...",
  "items": ["item1", "item2", "item3"],
  "solution": ["correct_order_item1", "correct_order_item2", "correct_order_item3"]
}
""",
    "selection": """
{
  "mechanic": "selection",
  "operation": "<operation_key>",
  "instruction_fr": "...",
  "instruction_en": "...",
  "options": ["opt1", "opt2", "opt3", "opt4"],
  "solution": "opt1"
}
""",
    "drag_drop": """
{
  "mechanic": "drag_drop",
  "operation": "<operation_key>",
  "instruction_fr": "...",
  "instruction_en": "...",
  "items": ["item1", "item2"],
  "zones": ["Zone A", "Zone B"],
  "solution": {"item1": "Zone A", "item2": "Zone B"}
}
""",
    "investigation": """
{
  "mechanic": "investigation",
  "operation": "<operation_key>",
  "instruction_fr": "...",
  "instruction_en": "...",
  "statements": [{"id": "s1", "text_fr": "...", "text_en": "..."}],
  "solution": {"s1": true, "s2": false}
}
Interface joueur : pastilles Vrai / Faux (une réponse par affirmation).
Affirmations courtes (≤ 120 car.) portant sur le rôle, l'usage ou la nature de l'objet/concept.
Mélanger affirmations vraies et fausses plausibles.
""",
}


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def build_challenge_exercise_prompt(
    *,
    question_context: dict[str, Any],
    mechanic: str,
    operation: str,
    pyramid_level: str,
    difficulty: int,
    lang: str | None,
) -> str:
    schema = MECHANIC_SCHEMAS.get(mechanic, MECHANIC_SCHEMAS["selection"])
    concepts = _json_list(question_context.get("concepts_vises"))
    prereqs = _json_list(question_context.get("prerequis_concepts"))
    proposition = question_context.get("proposition_summary") or ""
    matching_rules = ""
    if mechanic == "matching":
        matching_rules = """
8. Mécanique matching : interface par pastilles cliquables (une réponse par ligne) — PAS de glisser-déposer.
9. instruction_fr / instruction_en : décrire l'association par CLIC sur la pastille ; interdiction de « glisser », « déposer », « droite/gauche », « drag », « drop ».
10. Mécanique matching : chaque réponse (right) doit être UNIQUE (pas de doublon).
11. Mélange les correspondances : l'ordre des paires dans « pairs » NE DOIT PAS refléter l'ordre des bonnes réponses (éviter alignement ligne 1 → réponse 1, etc.).
"""
    investigation_rules = ""
    if mechanic == "investigation":
        investigation_rules = """
8. Mécanique investigation (enquête) : affirmations Vrai/Faux sur le rôle, l'usage, la nature de l'objet/concept.
9. Chaque affirmation a un id unique (s1, s2…) et solution booléenne (true/false).
10. Formuler des affirmations du type « X permet d'afficher… », « X fait partie de la solution… », « X sert à… ».
11. Inclure 1 à 2 fausses affirmations plausibles (distracteurs) par difficulté ≥ 2.
12. Interface : pastilles Vrai / Faux — PAS de glisser-déposer.
"""

    return (
        prompt_prefix(lang)
        + PYRAMID_CONSTITUTION
        + f"""
Tu es un expert en ingénierie pédagogique et conception de jeux éducatifs pour Terra-Cogitia.

OBJECTIF : générer un exercice ludique évaluatif à partir de l'objet de connaissance ci-dessous.

PARAMÈTRES DU DÉFI :
- Mécanique de jeu imposée : {mechanic}
- Opération cognitive cible : {operation}
- Niveau pyramide visé : {pyramid_level}
- Difficulté (1=facile, 5=exigeant) : {difficulty}

CONTEXTE PÉDAGOGIQUE :
- Question : {question_context.get("libelle") or ""}
- Objectif pédagogique : {question_context.get("objectif_pedagogique") or "non renseigné"}
- Concepts visés : {json.dumps(concepts, ensure_ascii=False)}
- Prérequis : {json.dumps(prereqs, ensure_ascii=False)}
- Parcours : {question_context.get("subtheme_label") or ""}
- Description parcours : {(question_context.get("subtheme_description") or "")[:400]}
- Proposition Discover (si disponible) : {proposition[:1200]}

CONTRAINTES :
1. L'exercice DOIT évaluer l'opération cognitive « {operation} » au niveau « {pyramid_level} ».
2. Évite la simple mémorisation : privilégie discrimination, relation, ordre ou choix argumenté.
3. Les items doivent être concrets, courts (≤ 80 caractères), en lien direct avec la question.
4. Inclure 1 à 2 distracteurs plausibles pour difficulty ≥ 2.
5. Nombre d'items : {2 + min(difficulty, 3)} à {3 + min(difficulty, 3)} selon la mécanique.
6. Les instructions FR et EN doivent être claires et actionnables.
7. Le champ « solution » doit être cohérent avec les items affichés (évaluable automatiquement).
{matching_rules}
{investigation_rules}
FORMAT DE SORTIE — JSON STRICT uniquement, sans markdown :
{schema}

IMPORTANT :
- Réponds avec du JSON STRICT uniquement (objet racine).
- N'ajoute AUCUN texte avant/après le JSON.
- « solution » doit permettre une correction automatique côté serveur.
"""
    )


def validate_exercise_content(content: dict[str, Any], mechanic: str, operation: str) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise ValueError("Le contenu doit être un objet JSON.")
    mech = str(content.get("mechanic") or mechanic)
    if mech != mechanic:
        raise ValueError(f"Mécanique attendue {mechanic}, reçue {mech}.")
    content["mechanic"] = mech
    content["operation"] = str(content.get("operation") or operation)
    if not content.get("instruction_fr") or not content.get("instruction_en"):
        raise ValueError("Instructions FR/EN manquantes.")

    solution = content.get("solution")
    if mech == "matching":
        pairs = content.get("pairs")
        if not isinstance(pairs, list) or len(pairs) < 2:
            raise ValueError("matching requiert au moins 2 paires.")
        expected: dict[str, str] = {}
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            left = str(pair.get("left") or "").strip()
            right = str(pair.get("right") or "").strip()
            if left and right:
                expected[left] = right
        if isinstance(solution, dict) and solution:
            content["solution"] = {str(k): str(v) for k, v in solution.items()}
        else:
            content["solution"] = expected
        if len(content["solution"]) < 2:
            raise ValueError("Solution matching invalide.")
        unique_rights = set(content["solution"].values())
        if len(unique_rights) != len(content["solution"]):
            raise ValueError("Chaque réponse matching doit être unique.")
        from challenge_framework.generator import normalize_matching_content

        normalize_matching_content(content, seed=json.dumps(content["solution"], sort_keys=True))
    elif mech == "sorting":
        items = content.get("items")
        if not isinstance(items, list) or len(items) < 2:
            raise ValueError("sorting requiert au moins 2 items.")
        if not isinstance(solution, list) or len(solution) != len(items):
            raise ValueError("Solution sorting doit être une permutation complète.")
        if set(solution) != set(items):
            raise ValueError("Solution sorting incohérente avec items.")
    elif mech == "drag_drop":
        items = content.get("items")
        zones = content.get("zones")
        if not isinstance(items, list) or not isinstance(zones, list):
            raise ValueError("drag_drop requiert items et zones.")
        if not isinstance(solution, dict):
            raise ValueError("Solution drag_drop doit être un objet item→zone.")
    elif mech == "investigation":
        statements = content.get("statements")
        if not isinstance(statements, list) or len(statements) < 3:
            raise ValueError("investigation requiert au moins 3 affirmations.")
        expected_bool: dict[str, bool] = {}
        for stmt in statements:
            if not isinstance(stmt, dict):
                continue
            sid = str(stmt.get("id") or "").strip()
            if sid:
                expected_bool[sid] = False
        if isinstance(solution, dict) and solution:
            for key, value in solution.items():
                expected_bool[str(key)] = bool(value)
        else:
            raise ValueError("Solution investigation invalide.")
        if len(expected_bool) < 3:
            raise ValueError("Solution investigation invalide.")
        content["solution"] = expected_bool
    else:
        options = content.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise ValueError("selection requiert au moins 2 options.")
        if solution not in options:
            raise ValueError("Solution selection absente des options.")
        content["mechanic"] = "selection"

    return content


async def call_mistral_challenge_exercise_json(prompt: str) -> dict[str, Any]:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("Variable d'environnement MISTRAL_API_KEY manquante ou vide.")
    client = Mistral(api_key=api_key, timeout_ms=MISTRAL_CHAT_TIMEOUT_MS)
    try:
        chat_response = await client.chat.complete_async(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=MISTRAL_DISCOVER_MAX_TOKENS,
            timeout_ms=MISTRAL_CHAT_TIMEOUT_MS,
        )
    except httpx.TimeoutException as e:
        raise ValueError("Délai Mistral dépassé pour la génération d'exercice.") from e
    except httpx.HTTPError as e:
        raise ValueError(f"Erreur HTTP Mistral : {e!s}") from e

    choices = getattr(chat_response, "choices", None) or []
    if not choices:
        raise ValueError("Réponse Mistral invalide.")
    response_text = mistral_message_content_to_text(getattr(choices[0].message, "content", None))
    if not response_text.strip():
        raise ValueError("Réponse Mistral vide.")
    return parse_json_object_from_llm_content(response_text)


async def generate_challenge_exercise_with_ai(
    *,
    question_context: dict[str, Any],
    mechanic: str,
    operation: str,
    pyramid_level: str,
    difficulty: int,
    lang: str | None = None,
) -> dict[str, Any]:
    prompt = build_challenge_exercise_prompt(
        question_context=question_context,
        mechanic=mechanic,
        operation=operation,
        pyramid_level=pyramid_level,
        difficulty=difficulty,
        lang=lang,
    )
    raw = await call_mistral_challenge_exercise_json(prompt)
    return validate_exercise_content(raw, mechanic, operation)


def _coerce_statut_current(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        return v in ("true", "t", "1", "yes", "oui")
    return False


async def load_question_context_for_ai(object_id: int) -> dict[str, Any]:
    from queries import postgres_select_query

    rows = await postgres_select_query(
        """
        SELECT q.id_question, q.libelle, q.operation_cognitive, q.niveau_pyramide,
               q.concepts_vises, q.objectif_pedagogique, q.prerequis_concepts,
               q.groupe, q.libelle_groupe,
               s.label AS subtheme_label, s.description AS subtheme_description,
               s.niveau_pyramide AS subtheme_pyramid
        FROM question q
        LEFT JOIN subtheme s ON s.id_subtheme = q.id_subtheme
        WHERE q.id_question = $1
        """,
        object_id,
    )
    if not rows:
        raise ValueError(f"Objet question {object_id} introuvable")
    ctx = dict(rows[0])
    ctx["niveau_pyramide"] = normalize_pyramid_level(ctx.get("niveau_pyramide")) or normalize_pyramid_level(
        ctx.get("subtheme_pyramid")
    )

    prop_rows = await postgres_select_query(
        """
        SELECT proposition, statut_current
        FROM proposition
        WHERE id_question = $1
        ORDER BY id_proposition DESC
        LIMIT 10
        """,
        object_id,
    )
    for row in prop_rows:
        data = dict(row)
        if not _coerce_statut_current(data.get("statut_current")):
            continue
        prop_val = data.get("proposition")
        summary = _summarize_proposition(prop_val)
        if summary:
            ctx["proposition_summary"] = summary
        break
    return ctx


def _summarize_proposition(value: Any) -> str:
    if value is None:
        return ""
    data: dict[str, Any] | None = None
    if isinstance(value, dict):
        data = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            return value[:1200]
    if not data:
        return ""
    parts: list[str] = []
    for key in ("introduction", "Introduction", "contexte", "Contexte", "analyse", "Analyse", "conclusion", "Conclusion"):
        if key in data and data[key]:
            parts.append(f"{key}: {str(data[key])[:300]}")
    return "\n".join(parts)[:1200]
