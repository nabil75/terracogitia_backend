from __future__ import annotations

import os
import json
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Query, status
import httpx

from discover_pexels import fetch_pexels_image_links_for_keywords, normalize_keywords_list
import database
from mistral.language_prompts import normalize_lang, prompt_prefix
from mistral.discovering_mistral import (
    MISTRAL_CHAT_TIMEOUT_MS as _MISTRAL_CHAT_TIMEOUT_MS,
    MISTRAL_DISCOVER_MAX_TOKENS as _MISTRAL_DISCOVER_MAX_TOKENS,
    call_discover_proposition_json as _call_discover_proposition_json_mistral,
    call_mistral_ordre_logique_json as _call_mistral_ordre_logique_json_mistral,
)
from queries import (
    postgres_insert_query,
    postgres_select_query,
    postgres_update_query,
)



import json
from typing import Any

from pydantic import BaseModel, Field

router = APIRouter(prefix="/discovering", tags=["discovering"])



class OrdreLogiqueQuestionIn(BaseModel):
    id: str | int
    label: str = Field(..., description="Ex. « Q1 - Libellé » — doit matcher les clés de sortie.")


class OrdreLogiqueQuestionsBody(BaseModel):
    id_subtheme: str
    questions: list[OrdreLogiqueQuestionIn]
    lang: Optional[Literal["fr", "en"]] = None


_ORDRE_LABEL_ID_SUFFIX_RE = re.compile(r"\s*\(id\s*=\s*(\d+)\s*\)\s*$", re.IGNORECASE)


# Fait: normalise un libellé pour comparaison insensible à la casse/accents.
# Entrées: `s` (str).
# Retour: `str`.
def _fold_label(s: str) -> str:
    """Compare les libellés Mistral / client (casse, espaces, accents)."""
    if not isinstance(s, str):
        s = str(s)
    nk = unicodedata.normalize("NFKD", s)
    nk = nk.encode("ascii", "ignore").decode("ascii")
    nk = re.sub(r"\s+", " ", nk).strip().lower()
    return nk


# Fait: supprime un suffixe d'identifiant dans un label d'ordre logique.
# Entrées: `label` (str).
# Retour: `str`.
def _strip_ordre_label_id_suffix(label: str) -> str:
    return _ORDRE_LABEL_ID_SUFFIX_RE.sub("", label.strip()).strip()


# Fait: extrait un identifiant de question depuis un label d'ordre logique.
# Entrées: `label` (str).
# Retour: `int | None`.
def _extract_id_from_ordre_label(label: str) -> int | None:
    m = _ORDRE_LABEL_ID_SUFFIX_RE.search(label.strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


# Fait: produit un libellé d'affichage standard pour l'ordre logique.
# Entrées: `label` (str).
# Retour: `str`.
def _display_ordre_label(label: str) -> str:
    """Libellé affichable : retire uniquement le suffixe « (id=…) » ajouté par Mistral."""
    return _strip_ordre_label_id_suffix(label)


# Fait: associe un label canonique à une ligne de question.
# Entrées: `label` (str), `row` (dict).
# Retour: `dict[str, Any]`.
def _label_to_question_row(
    questions: list[OrdreLogiqueQuestionIn],
) -> tuple[
    dict[str, OrdreLogiqueQuestionIn],
    dict[str, OrdreLogiqueQuestionIn],
    dict[int, OrdreLogiqueQuestionIn],
]:
    """(libellé exact -> q, libellé replié -> q, id_question -> q)."""
    by_exact: dict[str, OrdreLogiqueQuestionIn] = {}
    by_fold: dict[str, OrdreLogiqueQuestionIn] = {}
    by_id: dict[int, OrdreLogiqueQuestionIn] = {}
    for q in questions:
        by_exact[q.label.strip()] = q
        by_fold.setdefault(_fold_label(q.label), q)
        by_fold.setdefault(_fold_label(_strip_ordre_label_id_suffix(q.label)), q)
        try:
            by_id[int(str(q.id).strip())] = q
        except (TypeError, ValueError):
            pass
    return by_exact, by_fold, by_id


# Fait: résout la question correspondant à un label d'ordre logique.
# Entrées: `label` (str), `questions_by_id` (dict), `questions_by_label` (dict).
# Retour: `dict[str, Any] | None`.
def _resolve_question_for_label(
    label: str,
    by_exact: dict[str, OrdreLogiqueQuestionIn],
    by_fold: dict[str, OrdreLogiqueQuestionIn],
    by_id: dict[int, OrdreLogiqueQuestionIn] | None = None,
) -> OrdreLogiqueQuestionIn | None:
    if not isinstance(label, str):
        return None
    s = label.strip()
    qid = _extract_id_from_ordre_label(s)
    if qid is not None and by_id and qid in by_id:
        return by_id[qid]
    if s in by_exact:
        return by_exact[s]
    stripped = _strip_ordre_label_id_suffix(s)
    if stripped in by_exact:
        return by_exact[stripped]
    hit = by_fold.get(_fold_label(s))
    if hit:
        return hit
    return by_fold.get(_fold_label(stripped))


# Fait: recherche un nœud de relation dans une structure JSON hétérogène.
# Entrées: `node` (Any), `target_label` (str).
# Retour: `dict[str, Any] | None`.
def _find_relation_node(
    lib: str,
    relations_par_libelle: dict[str, Any],
    by_exact: dict[str, OrdreLogiqueQuestionIn],
    by_fold: dict[str, OrdreLogiqueQuestionIn],
    by_id: dict[int, OrdreLogiqueQuestionIn],
) -> Any:
    node = relations_par_libelle.get(lib)
    if node is not None:
        return node
    q = by_exact.get(lib)
    if q is not None:
        try:
            qid = int(str(q.id).strip())
            for k, v in relations_par_libelle.items():
                if isinstance(k, str) and _extract_id_from_ordre_label(k) == qid:
                    return v
        except (TypeError, ValueError):
            pass
    for k, v in relations_par_libelle.items():
        if not isinstance(k, str):
            continue
        if _fold_label(k) == _fold_label(lib):
            return v
        if _fold_label(_strip_ordre_label_id_suffix(k)) == _fold_label(lib):
            return v
    return None


# Fait: extrait les entrées de prérequis d'un nœud relation.
# Entrées: `node` (Any).
# Retour: `list[dict[str, Any]]`.
def _extract_prerequis_entries(node: Any) -> list[dict[str, Any]]:
    """Tolère pre-requis / prerequis / clés voisines renvoyées par le LLM."""
    if not isinstance(node, dict):
        return []
    for key in (
        "pre-requis",
        "pre_requis",
        "prerequis",
        "prérequis",
        "prereq",
        "prerequisites",
    ):
        raw = node.get(key)
        if raw is None:
            continue
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict):
            return [raw]
    return []


# Fait: construit des vues de lecture de l'ordre logique pour l'UI.
# Entrées: `questions` (list), `relations` (dict).
# Retour: `dict[str, Any]`.
def build_ordre_logique_vues_lecture(
    body: OrdreLogiqueQuestionsBody,
    relations_par_libelle: dict[str, Any],
) -> dict[str, Any]:
    """
    Structures pour une UI lisible sans graphe forcé : liste ordonnée + tableau de liens
    (prérequis → question dépendante + justification).
    """
    by_exact, by_fold, by_id = _label_to_question_row(body.questions)
    liste_par_parcours: list[dict[str, Any]] = []
    liens_plats: list[dict[str, Any]] = []

    for q in body.questions:
        lib = q.label.strip()
        node = _find_relation_node(lib, relations_par_libelle, by_exact, by_fold, by_id)
        prereqs_out: list[dict[str, Any]] = []
        for item in _extract_prerequis_entries(node):
            lbl = item.get("label") or item.get("libelle") or item.get("question")
            if not isinstance(lbl, str):
                continue
            lbl = lbl.strip()
            pq = _resolve_question_for_label(lbl, by_exact, by_fold, by_id)
            just = item.get("justification") or item.get("motif") or item.get("raison")
            if isinstance(just, (dict, list)):
                just = json.dumps(just, ensure_ascii=False)
            elif just is not None:
                just = str(just).strip()
            else:
                just = ""
            prereqs_out.append(
                {
                    "id": pq.id if pq else None,
                    "label": lbl,
                    "label_court": _display_ordre_label(lbl),
                    "justification": just,
                }
            )
            liens_plats.append(
                {
                    "id_prerequis": pq.id if pq else None,
                    "libelle_prerequis": lbl.strip(),
                    "id_question": q.id,
                    "libelle_question": lib,
                    "justification": just,
                }
            )
        liste_par_parcours.append(
            {
                "id": q.id,
                "label": lib,
                "prerequis": prereqs_out,
                "prerequis_resume": [p["label_court"] for p in prereqs_out],
            }
        )

    return {
        "liste_par_parcours": liste_par_parcours,
        "liens_plats": liens_plats,
        "conseil_ui": (
            "Pour une lecture confortable, privilégier un tableau « prérequis → question » "
            "ou une liste accordéon par question plutôt qu’un graphe de nœuds ; chaque ligne "
            "de liens_plats expose la justification."
        ),
    }


# Fait: parse et valide un identifiant de sous-thème.
# Entrées: `raw` (str | int).
# Retour: `int`.
def _parse_subtheme_id(raw: str | int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="id_subtheme invalide.")
    if n < 1:
        raise HTTPException(status_code=400, detail="id_subtheme invalide.")
    return n


# Fait: calcule une signature triée des ids question.
# Entrées: `questions` (list[OrdreLogiqueQuestionIn]).
# Retour: `list[int]`.
def _question_ids_signature(questions: list[OrdreLogiqueQuestionIn]) -> list[int]:
    out: list[int] = []
    for q in questions:
        try:
            out.append(int(str(q.id).strip()))
        except (TypeError, ValueError):
            continue
    return sorted(out)


# Fait: compare la signature questions courante avec celle d'une timeline stockée.
# Entrées: `timeline_doc` (dict), `questions` (list).
# Retour: `bool`.
def _timeline_signature_matches(
    stored: dict[str, Any], questions: list[OrdreLogiqueQuestionIn]
) -> bool:
    stored_ids = stored.get("question_ids")
    if not isinstance(stored_ids, list) or len(stored_ids) == 0:
        return False
    try:
        a = sorted(int(x) for x in stored_ids)
    except (TypeError, ValueError):
        return False
    return a == _question_ids_signature(questions)


# Fait: charge la timeline persistée d'un sous-thème.
# Entrées: `id_subtheme` (int).
# Retour: `dict[str, Any] | None`.
async def _fetch_subtheme_timeline(id_subtheme: int) -> dict[str, Any] | None:
    rows = await postgres_select_query(
        "SELECT timeline FROM subtheme WHERE id_subtheme = $1",
        id_subtheme,
    )
    if not rows:
        return None
    raw = rows[0].get("timeline")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, dict):
        return raw
    return None


# Fait: enregistre la timeline d'un sous-thème en base.
# Entrées: `id_subtheme` (int), `doc` (dict).
# Retour: `None`.
async def _save_subtheme_timeline(id_subtheme: int, doc: dict[str, Any]) -> None:
    payload = json.dumps(doc, ensure_ascii=False)
    await postgres_update_query(
        "UPDATE subtheme SET timeline = $1::jsonb WHERE id_subtheme = $2",
        payload,
        id_subtheme,
    )


# Fait: normalise un libellé de parcours pour le tri/égalité.
# Entrées: `label` (str).
# Retour: `str`.
def _canonical_parcours_label(
    label: str,
    by_exact: dict[str, OrdreLogiqueQuestionIn],
    by_fold: dict[str, OrdreLogiqueQuestionIn],
    by_id: dict[int, OrdreLogiqueQuestionIn],
) -> str | None:
    q = _resolve_question_for_label(label, by_exact, by_fold, by_id)
    return q.label.strip() if q else None


# Fait: construit les arêtes d'un graphe à partir des relations.
# Entrées: `relations` (dict), `labels` (list[str]).
# Retour: `list[tuple[str, str]]`.
def _edges_from_relations(
    body: OrdreLogiqueQuestionsBody, relations: dict[str, Any]
) -> list[tuple[str, str]]:
    by_exact, by_fold, by_id = _label_to_question_row(body.questions)
    edges: list[tuple[str, str]] = []
    seen: set[str] = set()
    for target_key, val in relations.items():
        if not isinstance(target_key, str):
            continue
        tk = _canonical_parcours_label(target_key.strip(), by_exact, by_fold, by_id)
        if not tk:
            continue
        for item in _extract_prerequis_entries(val):
            lbl = item.get("label") or item.get("libelle")
            if not isinstance(lbl, str):
                continue
            src = _canonical_parcours_label(lbl.strip(), by_exact, by_fold, by_id)
            if not src or src == tk:
                continue
            key = f"{src}\0{tk}"
            if key in seen:
                continue
            seen.add(key)
            edges.append((src, tk))
    return edges


# Fait: applique un tri topologique sur des labels.
# Entrées: `nodes` (list[str]), `edges` (list[tuple[str, str]]).
# Retour: `list[str]`.
def _topological_sort_labels(
    label_list: list[str], edges: list[tuple[str, str]]
) -> tuple[list[str], bool]:
    nodes = [s.strip() for s in label_list if s.strip()]
    rank = {n: i for i, n in enumerate(nodes)}
    indegree = {n: 0 for n in nodes}
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for u, v in edges:
        u, v = u.strip(), v.strip()
        if u not in rank or v not in rank or u == v:
            continue
        adj[u].append(v)
        indegree[v] = indegree.get(v, 0) + 1
    order: list[str] = []
    remaining = set(nodes)

    def by_rank(a: str, b: str) -> int:
        ra, rb = rank[a], rank[b]
        if ra != rb:
            return ra - rb
        return (a > b) - (a < b)

    while remaining:
        zeros = sorted([n for n in remaining if indegree.get(n, 0) == 0], key=lambda x: rank[x])
        if not zeros:
            break
        for n in zeros:
            order.append(n)
            remaining.discard(n)
            for v in adj.get(n, []):
                indegree[v] = indegree.get(v, 0) - 1
    partial = len(remaining) > 0
    if partial:
        order.extend(sorted(remaining, key=lambda x: rank[x]))
    return order, partial


# Fait: convertit un ordre de labels en étapes séquencées.
# Entrées: `ordered_labels` (list[str]), `questions_by_label` (dict).
# Retour: `list[dict[str, Any]]`.
def _build_sequence_steps(
    body: OrdreLogiqueQuestionsBody,
    relations: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    label_list = [q.label.strip() for q in body.questions]
    edges = _edges_from_relations(body, relations)
    if not edges:
        return (
            [
                {
                    "step": i + 1,
                    "id": q.id,
                    "label": q.label.strip(),
                }
                for i, q in enumerate(body.questions)
            ],
            False,
        )
    order, partial = _topological_sort_labels(label_list, edges)
    by_label = {q.label.strip(): q for q in body.questions}
    steps: list[dict[str, Any]] = []
    for i, lbl in enumerate(order):
        q = by_label.get(lbl)
        if not q:
            continue
        steps.append({"step": len(steps) + 1, "id": q.id, "label": lbl})
    return steps, partial


# Fait: construit le document timeline complet à persister.
# Entrées: `questions` (list), `relations` (dict), `sequence_steps` (list).
# Retour: `dict[str, Any]`.
def _build_timeline_document(
    body: OrdreLogiqueQuestionsBody,
    relations: dict[str, Any],
    vues: dict[str, Any],
    sequence: list[dict[str, Any]],
    partial: bool,
) -> dict[str, Any]:
    return {
        "version": 1,
        "question_ids": _question_ids_signature(body.questions),
        "relations_par_libelle": relations,
        "liste_par_parcours": vues.get("liste_par_parcours", []),
        "liens_plats": vues.get("liens_plats", []),
        "conseil_ui": vues.get("conseil_ui"),
        "sequence": sequence,
        "partial": partial,
    }


# Fait: convertit un document timeline en réponse API enrichie.
# Entrées: `doc` (dict).
# Retour: `dict[str, Any]`.
def _enriched_response_from_timeline(
    id_subtheme: int, doc: dict[str, Any], *, from_cache: bool
) -> dict[str, Any]:
    return {
        "id_subtheme": id_subtheme,
        "from_cache": from_cache,
        "relations_par_libelle": doc.get("relations_par_libelle") or {},
        "liste_par_parcours": doc.get("liste_par_parcours") or [],
        "liens_plats": doc.get("liens_plats") or [],
        "conseil_ui": doc.get("conseil_ui"),
        "sequence": doc.get("sequence") or [],
        "partial": bool(doc.get("partial")),
    }


# Fait: charge la timeline existante ou la reconstruit si nécessaire.
# Entrées: `id_subtheme` (int), `questions` (list), `relations` (dict), `force_refresh` (bool).
# Retour: `dict[str, Any]`.
async def _load_or_build_ordre_logique(
    body: OrdreLogiqueQuestionsBody, *, force_refresh: bool
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    """Retourne (réponse enrichie, document timeline, from_cache) — format enrichi uniquement."""
    id_subtheme = _parse_subtheme_id(body.id_subtheme)
    if not force_refresh:
        cached = await _fetch_subtheme_timeline(id_subtheme)
        if cached and _timeline_signature_matches(cached, body.questions):
            return _enriched_response_from_timeline(id_subtheme, cached, from_cache=True), cached, True

    prompt = build_ordre_logique_prompt(body)
    data = await call_mistral_ordre_logique_json(prompt)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Réponse Mistral non objet JSON")
    vues = build_ordre_logique_vues_lecture(body, data)
    sequence, partial = _build_sequence_steps(body, data)
    doc = _build_timeline_document(body, data, vues, sequence, partial)
    await _save_subtheme_timeline(id_subtheme, doc)
    enriched = _enriched_response_from_timeline(id_subtheme, doc, from_cache=False)
    return enriched, doc, False


_ID_QUESTION_KEYS = (
    "idQuestion",
    "id_question",
    "questionId",
    "question_id",
    "id",
)

_PROPOSITION_OBJ_KEYS = (
    "proposition",
    "proposition_payload",
    "propositionPayload",
    "discoverProposition",
    "savedDiscoverProposition",
    "saved_discover_proposition",
    "payload",
    "discover",
    "content",
)


# Fait: déplie un payload optionnellement encapsulé (`data`, `body`, ...).
# Entrées: `raw` (Dict[str, Any]).
# Retour: `Dict[str, Any]`.
def _unwrap_payload_container(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Déplie les enveloppes fréquentes uniquement si l'intérieur porte l'id question,
    pour ne pas écraser un corps plat du type { idQuestion, payload: { ...json... } }.
    """
    if not isinstance(raw, dict):
        raise ValueError("Le corps de la requête doit être un objet JSON.")
    for key in ("data", "body", "request", "payload"):
        inner = raw.get(key)
        if isinstance(inner, dict) and any(
            id_key in inner for id_key in _ID_QUESTION_KEYS
        ):
            return inner
    return raw


# Fait: convertit une valeur brute en id question valide.
# Entrées: `value` (Any).
# Retour: `int`.
def _coerce_question_id(value: Any) -> int:
    if value is None:
        raise ValueError("Identifiant de question manquant.")
    if isinstance(value, bool):
        raise ValueError("Identifiant de question invalide.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError("Identifiant de question vide.")
        try:
            return int(s)
        except ValueError as e:
            raise ValueError(
                "Identifiant de question invalide (entier attendu)."
            ) from e
    raise ValueError("Identifiant de question invalide.")


# Fait: convertit un payload proposition en dictionnaire.
# Entrées: `value` (Any).
# Retour: `Dict[str, Any]`.
def _coerce_proposition_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                "proposition doit être un objet JSON ou une chaîne JSON objet valide."
            ) from e
        if not isinstance(parsed, dict):
            raise ValueError(
                "proposition JSON doit être un objet (pas un tableau ni une valeur simple)."
            )
        return parsed
    raise ValueError(
        "proposition doit être un objet ou une chaîne JSON représentant un objet."
    )


# Fait: extrait `id_question` et contenu proposition d'un payload de sauvegarde.
# Entrées: `raw` (Dict[str, Any]).
# Retour: `tuple[int, Dict[str, Any]]`.
def _extract_store_saved_payload(raw: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    """
    Extrait (id_question, proposition) pour api.storeSavedDiscoverProposition.
    Tolère plusieurs formes de corps Angular sans validation Pydantic stricte.
    """
    data = _unwrap_payload_container(raw)

    id_question: Optional[int] = None
    for key in _ID_QUESTION_KEYS:
        if key in data and data[key] is not None:
            id_question = _coerce_question_id(data[key])
            break
    if id_question is None:
        raise ValueError(
            "Champ identifiant question introuvable. Utiliser idQuestion, id_question, "
            "questionId ou question_id."
        )

    proposition: Optional[Dict[str, Any]] = None
    for key in _PROPOSITION_OBJ_KEYS:
        if key in data:
            proposition = _coerce_proposition_dict(data[key])
            break

    if proposition is None:
        skip = set(_ID_QUESTION_KEYS) | {"data", "body", "request"}
        rest = {k: v for k, v in data.items() if k not in skip}
        if rest:
            proposition = _coerce_proposition_dict(rest)

    if proposition is None:
        raise ValueError(
            "Contenu proposition introuvable. Utiliser la clé proposition / discoverProposition "
            "ou envoyer les sections Discover à la racine du corps."
        )

    return id_question, proposition


# Fait: convertit un statut courant hétérogène en booléen fiable.
# Entrées: `value` (Any).
# Retour: `bool`.
def _coerce_statut_current(value: Any) -> bool:
    """Interprète statut_current sans traiter une chaîne 'false' comme vraie (bool('false') == True)."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "t", "1", "yes", "oui"):
            return True
        if v in ("false", "f", "0", "no", "non", ""):
            return False
        return False
    return False


_EMPTY_DISCOVER_PROPOSITION_PAYLOAD: Dict[str, Any] = {
    "discoveredProposition": "",
    "discoveredKeyPoints": [],
    "discoveredStructured": None,
}


# Fait: met à jour/crée les notes sur la proposition courante d'une question.
# Entrées: `id_question` (int), `notes` (str).
# Retour: `Dict[str, Any]`.
async def _upsert_notes_on_current_proposition(id_question: int, notes: str) -> Dict[str, Any]:
    """
    Enregistre les notes sur la proposition courante de la question.
    Crée une ligne minimale (proposition vide) si aucune proposition courante n'existe encore.
    """
    await _normalize_statut_current_for_question(id_question)
    rows = await postgres_select_query(
        """
        SELECT id_proposition, statut_current
        FROM proposition
        WHERE id_question = $1
        ORDER BY id_proposition DESC
        """,
        id_question,
    )
    current_id: int | None = None
    for row in rows:
        if _coerce_statut_current(row.get("statut_current")):
            current_id = int(row["id_proposition"])
            break

    if current_id is not None:
        updated = await postgres_select_query(
            """
            UPDATE proposition
            SET notes = $1
            WHERE id_proposition = $2
            RETURNING id_proposition, id_question, notes
            """,
            notes,
            current_id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Proposition introuvable.")
        row = updated[0]
        return {
            "id_proposition": row["id_proposition"],
            "id_question": row["id_question"],
            "notes": row.get("notes") or "",
        }

    if not notes.strip():
        return {
            "id_proposition": None,
            "id_question": id_question,
            "notes": "",
        }

    new_id, _date_creation = await _insert_proposition_as_current(
        id_question,
        _EMPTY_DISCOVER_PROPOSITION_PAYLOAD,
        notes,
    )
    return {
        "id_proposition": new_id,
        "id_question": id_question,
        "notes": notes,
    }


# Fait: garantit qu'une seule proposition est marquée courante pour la question.
# Entrées: `id_question` (int).
# Retour: `None`.
async def _normalize_statut_current_for_question(id_question: int) -> None:
    """Une seule ligne ``statut_current = true`` par question (la plus récente si ambiguïté)."""
    if database.pool is None:
        return
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id_proposition, statut_current
                FROM proposition
                WHERE id_question = $1
                ORDER BY id_proposition DESC
                """,
                id_question,
            )
            if not rows:
                return
            current_ids = [
                int(r["id_proposition"])
                for r in rows
                if _coerce_statut_current(r["statut_current"])
            ]
            if len(current_ids) == 1:
                return
            keep_id = int(rows[0]["id_proposition"]) if not current_ids else max(current_ids)
            await conn.execute(
                """
                UPDATE proposition
                SET statut_current = (id_proposition = $1)
                WHERE id_question = $2
                """,
                keep_id,
                id_question,
            )


# Fait: génère la date de création d'une proposition au format UI.
# Entrées: aucune.
# Retour: `str`.
def _proposition_date_creation_now() -> str:
    """Horodatage de sauvegarde au format JJ/MM/AAAA HH:MM."""
    return datetime.now().strftime("%d/%m/%Y %H:%M")


# Fait: insère une proposition et la marque courante.
# Entrées: `id_question` (int), `proposition` (dict), `notes` (str | None).
# Retour: `tuple[int, str]`.
async def _insert_proposition_as_current(
    id_question: int,
    proposition: Dict[str, Any],
    notes: str | None = None,
) -> tuple[int, str]:
    if database.pool is None:
        raise HTTPException(
            status_code=500, detail="Pool base de données non initialisé."
        )
    payload_json = json.dumps(proposition, ensure_ascii=False)
    date_creation = _proposition_date_creation_now()
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            new_id = await conn.fetchval(
                """
                INSERT INTO proposition (
                    id_question, proposition, statut_current, notes, date_creation
                )
                VALUES ($1, $2::jsonb, true, $3, $4)
                RETURNING id_proposition
                """,
                id_question,
                payload_json,
                notes or "",
                date_creation,
            )
            await conn.execute(
                """
                UPDATE proposition
                SET statut_current = false
                WHERE id_question = $1 AND id_proposition <> $2
                """,
                id_question,
                new_id,
            )
            return int(new_id), date_creation


# Fait: positionne une proposition donnée comme courante.
# Entrées: `id_proposition` (int).
# Retour: `int` (id_question associé).
async def _set_proposition_current(id_proposition: int) -> int:
    if database.pool is None:
        raise HTTPException(
            status_code=500, detail="Pool base de données non initialisé."
        )
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id_question
                FROM proposition
                WHERE id_proposition = $1
                """,
                id_proposition,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Proposition introuvable.")
            id_question = int(row["id_question"])
            await conn.execute(
                """
                UPDATE proposition
                SET statut_current = false
                WHERE id_question = $1
                """,
                id_question,
            )
            await conn.execute(
                """
                UPDATE proposition
                SET statut_current = true
                WHERE id_proposition = $1
                """,
                id_proposition,
            )
            return id_question


# Fait: promeut la proposition la plus récente en courante.
# Entrées: `id_question` (int).
# Retour: `None`.
async def _promote_latest_proposition_current(id_question: int) -> None:
    if database.pool is None:
        return
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            latest = await conn.fetchval(
                """
                SELECT id_proposition
                FROM proposition
                WHERE id_question = $1
                ORDER BY id_proposition DESC
                LIMIT 1
                """,
                id_question,
            )
            await conn.execute(
                """
                UPDATE proposition
                SET statut_current = false
                WHERE id_question = $1
                """,
                id_question,
            )
            if latest is not None:
                await conn.execute(
                    """
                    UPDATE proposition
                    SET statut_current = true
                    WHERE id_proposition = $1
                    """,
                    latest,
                )


# Fait: convertit une cellule JSONB proposition vers dict Python.
# Entrées: `value` (Any).
# Retour: `Dict[str, Any]`.
def _jsonb_proposition_cell_to_dict(value: Any) -> Dict[str, Any]:
    """
    Colonne PostgreSQL `jsonb` : asyncpg renvoie en général un dict, mais selon
    driver / casting on peut recevoir une str JSON. `dict(str)` itère caractère par
    caractère et provoque : « element #0 has length 1; 2 is required ».
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return {"_raw": s}
        if isinstance(parsed, dict):
            return parsed
        return {"_data": parsed}
    return {}


# Le SDK Mistral applique 30 s par défaut si timeout_ms est absent — trop court pour
# mistral-large + réponse JSON structurée longue (ReadTimeout côté httpx).
_MISTRAL_CHAT_TIMEOUT_MS = _MISTRAL_CHAT_TIMEOUT_MS
_MISTRAL_DISCOVER_MAX_TOKENS = _MISTRAL_DISCOVER_MAX_TOKENS


# Fait: normalise une clé de champ textuel Discover.
# Entrées: `key` (str).
# Retour: `str`.
def _normalize_field_key(key: str) -> str:
    if not isinstance(key, str):
        key = str(key)
    nk = unicodedata.normalize("NFKD", key)
    nk = nk.encode("ascii", "ignore").decode("ascii")
    nk = re.sub(r"\s+", "", nk)
    return nk.lower().strip()


# Fait: convertit une valeur quelconque en texte de section exploitable.
# Entrées: `value` (Any).
# Retour: `str`.
def _coerce_section_text(value) -> str:
    """Normalise str / list / dict Mistral en un seul bloc de texte non vide."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value).strip()
    if isinstance(value, list):
        parts = [_coerce_section_text(item) for item in value]
        return "\n".join(p for p in parts if p)
    if isinstance(value, dict):
        chunks: List[str] = []
        for sub_v in value.values():
            t = _coerce_section_text(sub_v)
            if t:
                chunks.append(t)
        return "\n\n".join(chunks)
    return str(value).strip()


# Fait: mappe une clé normalisée vers un bucket de section canonique.
# Entrées: `normalized_key` (str).
# Retour: `Optional[str]`.
def _canonical_section_bucket(normalized_key: str) -> Optional[str]:
    if normalized_key in ("introduction", "intro"):
        return "introduction"
    if normalized_key in ("contexte", "context"):
        return "contexte"
    if normalized_key in ("analyse", "analysis"):
        return "analyse"
    if normalized_key in ("conclusion",):
        return "conclusion"
    if normalized_key in (
        "exercice",
        "exercise",
        "activite",
        "activity",
        "tp",
        "travailpratique",
        "travail_pratique",
    ):
        return "exercice"
    if "analys" in normalized_key:
        return "analyse"
    if "exercic" in normalized_key or "exercise" in normalized_key:
        return "exercice"
    return None


# Fait: parcourt récursivement un objet et accumule les sections textuelles.
# Entrées: `obj` (Any), `buckets` (Dict[str, List[str]]).
# Retour: `None`.
def _accumulate_sections_recursive(obj, buckets: Dict[str, List[str]]) -> None:
    """Parcourt tout le JSON : sections souvent imbriquées ou sous d'autres clés."""
    if isinstance(obj, dict):
        for raw_k, raw_v in obj.items():
            nk = _normalize_field_key(raw_k)
            if _is_discover_metadata_field_key(nk):
                continue
            bucket = _canonical_section_bucket(nk)
            if bucket is not None:
                text = _coerce_section_text(raw_v)
                if text:
                    buckets[bucket].append(text)
            if isinstance(raw_v, (dict, list)):
                _accumulate_sections_recursive(raw_v, buckets)
    elif isinstance(obj, list):
        for item in obj:
            _accumulate_sections_recursive(item, buckets)


# Fait: indique si une clé correspond à un champ de métadonnées Discover.
# Entrées: `normalized_key` (str).
# Retour: `bool`.
def _is_discover_metadata_field_key(normalized_key: str) -> bool:
    return (
        "liensimages" in normalized_key
        or "imagelinks" in normalized_key
        or "motscles" in normalized_key
        or normalized_key.endswith("keywords")
        or normalized_key.endswith("keyword")
    )


# Fait: extrait des mots-clés d'images pour une section Discover.
# Entrées: `response_json` (dict), `section` (str).
# Retour: `List[str]`.
def _extract_section_keywords(response_json: dict, section: str) -> List[str]:
    """Extrait 4–5 mots-clés Mistral pour contexte ou analyse."""
    if not isinstance(response_json, dict):
        return []
    aliases = {
        "contexte": (
            "contexte_mots_cles",
            "contexteMotsCles",
            "Contexte_mots_cles",
            "contexte_mots_cle",
            "contexteMotsCle",
            "mots_cles_contexte",
            "contexte_keywords",
            "contexteKeywords",
        ),
        "analyse": (
            "analyse_mots_cles",
            "analyseMotsCles",
            "Analyse_mots_cles",
            "analyse_mots_cle",
            "analyseMotsCle",
            "mots_cles_analyse",
            "analyse_keywords",
            "analyseKeywords",
        ),
    }
    for k in aliases.get(section, ()):
        if k in response_json:
            return normalize_keywords_list(response_json[k])
    target = f"{section}motscles"
    for raw_k, raw_v in response_json.items():
        if _normalize_field_key(raw_k) == target:
            return normalize_keywords_list(raw_v)
    return []


# Fait: enrichit la réponse Discover avec des liens images Pexels.
# Entrées: `response_json` (dict), `lang` (str).
# Retour: `dict`.
async def _attach_pexels_images_to_discover_result(
    result: dict, response_json: dict
) -> dict:
    """Enrichit la réponse avec les liens images Pexels stockés (CDN/S3 ou local)."""
    contexte_kw = _extract_section_keywords(response_json, "contexte")
    analyse_kw = _extract_section_keywords(response_json, "analyse")

    try:
        contexte_liens = await fetch_pexels_image_links_for_keywords(contexte_kw)
        analyse_liens = await fetch_pexels_image_links_for_keywords(analyse_kw)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    result["contexte_mots_cles"] = contexte_kw
    result["analyse_mots_cles"] = analyse_kw
    result["contexte_liens_images"] = contexte_liens
    result["analyse_liens_images"] = analyse_liens
    result["contexteLiensImages"] = contexte_liens
    result["analyseLiensImages"] = analyse_liens
    return result


# Fait: extrait et structure les sections d'une réponse Discover.
# Entrées: `response_json` (dict).
# Retour: `dict`.
def _extract_discover_sections(response_json: dict) -> dict:
    buckets: Dict[str, List[str]] = {
        "introduction": [],
        "contexte": [],
        "analyse": [],
        "conclusion": [],
        "exercice": [],
    }
    _accumulate_sections_recursive(response_json, buckets)

    introduction = "\n\n".join(buckets["introduction"]).strip()
    contexte = "\n\n".join(buckets["contexte"]).strip()
    analyse = "\n\n".join(buckets["analyse"]).strip()
    conclusion = "\n\n".join(buckets["conclusion"]).strip()
    exercice = "\n\n".join(buckets["exercice"]).strip()

    return {
        "introduction": introduction,
        "Contexte": contexte,
        "Analyse": analyse,
        "analyse": analyse,
        "Conclusion": conclusion,
        "exercice": exercice,
        "Exercice": exercice,
    }


# Fait: retourne les propositions sauvegardées d'une question.
# Entrées: `id_question` (int).
# Retour: `list[dict]`.
@router.get("/get_saved_propositions_by_question/{id_question}")
async def get_saved_propositions_by_question(id_question: int):
    """
    Retourne toutes les propositions sauvegardées pour une question (`table proposition`).

    Appel front typique : ``api.getSavedDiscoverPropositionsByQuestion(idQuestion)``.

    URLs équivalentes (préfixe router ``/discovering``)::

        GET /discovering/get_saved_propositions_by_question/{id_question}
        GET /discovering/get_saved_discover_propositions_by_question/{id_question}
    """
    try:
        await _normalize_statut_current_for_question(id_question)
        rows = await postgres_select_query(
            """
            SELECT
                p.id_proposition,
                p.id_question,
                p.proposition,
                p.statut_current,
                p.notes,
                p.date_creation
            FROM proposition p
            WHERE p.id_question = $1
            ORDER BY p.id_proposition DESC
            """,
            id_question,
        )
        return [
            {
                "id_proposition": row["id_proposition"],
                "id_question": row["id_question"],
                "proposition": _jsonb_proposition_cell_to_dict(row["proposition"]),
                "statut_current": _coerce_statut_current(row.get("statut_current")),
                "notes": row.get("notes") or "",
                "date_creation": row.get("date_creation") or "",
            }
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération des propositions sauvegardées : {e!s}",
        )


@router.delete(
    "/delete_saved_proposition/{id_proposition}",
    status_code=status.HTTP_204_NO_CONTENT,
)
# Fait: supprime une proposition par identifiant.
# Entrées: `id_proposition` (int).
# Retour: `None`.
async def delete_saved_proposition(id_proposition: int):
    """
    Supprime une ligne ``proposition`` par sa clé primaire ``id_proposition``
    (valeur renvoyée par ``GET .../get_saved_propositions_by_question/...``).

    Appel front typique : ``api.deleteSavedDiscoverProposition(idProposition)``.
    """
    try:
        if database.pool is None:
            raise HTTPException(
                status_code=500, detail="Pool base de données non initialisé."
            )
        async with database.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    DELETE FROM proposition
                    WHERE id_proposition = $1
                    RETURNING id_question, statut_current
                    """,
                    id_proposition,
                )
                if not row:
                    raise HTTPException(
                        status_code=404,
                        detail="Proposition introuvable.",
                    )
                if bool(row["statut_current"]):
                    id_q = int(row["id_question"])
                    latest = await conn.fetchval(
                        """
                        SELECT id_proposition
                        FROM proposition
                        WHERE id_question = $1
                        ORDER BY id_proposition DESC
                        LIMIT 1
                        """,
                        id_q,
                    )
                    await conn.execute(
                        """
                        UPDATE proposition
                        SET statut_current = false
                        WHERE id_question = $1
                        """,
                        id_q,
                    )
                    if latest is not None:
                        await conn.execute(
                            """
                            UPDATE proposition
                            SET statut_current = true
                            WHERE id_proposition = $1
                            """,
                            latest,
                        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la suppression de la proposition : {e!s}",
        )


# Fait: enregistre une proposition Discover comme courante.
# Entrées: `body` (Dict[str, Any]).
# Retour: `dict`.
@router.post("/store_saved_proposition", status_code=status.HTTP_201_CREATED)
async def store_saved_proposition(body: Dict[str, Any] = Body(...)):
    """
    Enregistre une proposition Discover dans la table `proposition`.
    Attendu par le front : api.storeSavedDiscoverProposition.
    """
    try:
        id_question, proposition = _extract_store_saved_payload(body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    notes_raw = body.get("notes")
    notes = notes_raw if isinstance(notes_raw, str) else ""

    try:
        new_id, date_creation = await _insert_proposition_as_current(
            id_question, proposition, notes
        )
        await _normalize_statut_current_for_question(id_question)
        return {
            "id_proposition": new_id,
            "id_question": id_question,
            "proposition": proposition,
            "statut_current": True,
            "notes": notes,
            "date_creation": date_creation,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'enregistrement de la proposition : {e!s}",
        )


@router.patch(
    "/set_current_proposition/{id_proposition}",
    status_code=status.HTTP_200_OK,
)
# Fait: définit une proposition existante comme courante.
# Entrées: `id_proposition` (int).
# Retour: `dict`.
async def set_current_proposition(id_proposition: int):
    """Marque une proposition comme courante pour sa question (une seule à la fois)."""
    try:
        id_question = await _set_proposition_current(id_proposition)
        await _normalize_statut_current_for_question(id_question)
        return {
            "id_proposition": id_proposition,
            "id_question": id_question,
            "statut_current": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du changement de proposition courante : {e!s}",
        )


# Fait: upsert des notes au niveau question/proposition courante.
# Entrées: `id_question` (int), `body` (Dict[str, Any]).
# Retour: `dict`.
@router.put("/question_proposition_notes/{id_question}", status_code=status.HTTP_200_OK)
async def upsert_question_proposition_notes(id_question: int, body: Dict[str, Any] = Body(...)):
    """
    Sauvegarde les notes dans ``proposition.notes`` pour la proposition courante de la question.
    Crée une proposition courante vide si nécessaire (notes seules).
    """
    notes = body.get("notes")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise HTTPException(status_code=422, detail="Le champ notes doit être une chaîne.")
    try:
        return await _upsert_notes_on_current_proposition(id_question, notes)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'enregistrement des notes : {e!s}",
        )


# Fait: génère une proposition Discover pour une question et un sous-thème.
# Entrées: `question` (str), `subtheme` (str).
# Retour: `dict`.
@router.get("/get_proposition_for_question/{question}/{subtheme}")
async def get_proposition_for_question(
    question: str,
    subtheme: str,
    lang: Optional[str] = Query(None, description="UI language: fr or en"),
):
    try:
        response_json = await _call_discover_proposition_json_mistral(
            subtheme, question, normalize_lang(lang)
        )
        result = _extract_discover_sections(response_json)
        result = await _attach_pexels_images_to_discover_result(result, response_json)
        required_keys = ["introduction", "Contexte", "Analyse", "Conclusion", "exercice"]
        if not any(result.get(k) for k in required_keys):
            raise ValueError("Le JSON ne contient pas les champs attendus.")
        if not result.get("Analyse") or not result.get("exercice"):
            raise ValueError(
                "Réponse Mistral incomplète : champs Analyse et/ou exercice vides "
                "(réponse probablement tronquée ou JSON non conforme)."
            )
        return result

    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))


# Fait: construit le prompt Mistral pour l'ordre logique des questions.
# Entrées: `body` (`OrdreLogiqueQuestionsBody`).
# Retour: `str`.
def build_ordre_logique_prompt(body: OrdreLogiqueQuestionsBody) -> str:
    lines = "\n".join(f"- {q.label} (id={q.id})" for q in body.questions)
    return f"""{prompt_prefix(body.lang)}
Tu es un expert en didactique. On te donne la liste ordonnée des questions d’un parcours d’apprentissage.
Pour CHAQUE question (identifiée par son libellé exact « Qn - … »), indique quelles AUTRES questions de la liste
doivent être comprises ou traitées AVANT celle-ci (prérequis conceptuels). Limite-toi aux questions fournies.
Si aucun prérequis, renvoie une liste vide.

Liste des questions :
{lines}

Réponds UNIQUEMENT avec un objet JSON valide UTF-8, sans markdown, de la forme :
{{
  "Q1 - …": {{
    "pre-requis": [
      {{ "label": "Qk - …", "justification": "…" }}
    ]
  }},
  "Q2 - …": {{ "pre-requis": [] }}
}}
Les clés de l’objet racine DOIVENT être exactement les libellés « Qn - … » fournis.
Chaque élément de pre-requis doit référencer un « label » présent dans la liste.
Pour chaque lien prérequis → question, le champ « justification » est OBLIGATOIRE : un court paragraphe
(2 à 5 phrases) expliquant en quoi la maîtrise de la question prérequis aide à comprendre la question cible
(ce texte sera affiché tel quel aux utilisateurs).
"""


# Fait: appelle Mistral et parse la réponse JSON d'ordre logique.
# Entrées: `prompt` (str).
# Retour: `dict[str, Any]`.
async def call_mistral_ordre_logique_json(prompt: str) -> dict[str, Any]:
    return await _call_mistral_ordre_logique_json_mistral(prompt)


# Fait: retourne la timeline persistée d'un sous-thème.
# Entrées: `subtheme_id` (int).
# Retour: `dict[str, Any]`.
@router.get("/subtheme_timeline/{subtheme_id}")
async def get_subtheme_timeline(subtheme_id: int) -> dict[str, Any]:
    """Timeline persistée pour un parcours (sans appel Mistral)."""
    doc = await _fetch_subtheme_timeline(subtheme_id)
    if not doc:
        return {"id_subtheme": subtheme_id, "from_cache": False}
    return _enriched_response_from_timeline(subtheme_id, doc, from_cache=True)


# Fait: calcule ou recharge l'ordre logique d'apprentissage d'un sous-thème.
# Entrées: `body` (`OrdreLogiqueQuestionsBody`), `legacy` (bool), `force_refresh` (bool).
# Retour: `dict[str, Any]`.
@router.post("/ordre_logique_questions")
async def ordre_logique_questions(
    body: OrdreLogiqueQuestionsBody,
    legacy: bool = Query(
        True,
        description=(
            "Si true (défaut), renvoie uniquement l'objet LLM d'origine (clés = libellés), "
            "comme auparavant. Si false, renvoie relations_par_libelle + liste_par_parcours, "
            "liens_plats (avec justifications) et conseil_ui pour une UI plus lisible."
        ),
    ),
    force_refresh: bool = Query(
        False,
        description="Si true, ignore la timeline en base et régénère via Mistral.",
    ),
) -> dict[str, Any]:
    if not body.questions:
        return {}
    try:
        if legacy:
            if not force_refresh:
                id_subtheme = _parse_subtheme_id(body.id_subtheme)
                cached = await _fetch_subtheme_timeline(id_subtheme)
                if cached and _timeline_signature_matches(cached, body.questions):
                    rel = cached.get("relations_par_libelle")
                    if isinstance(rel, dict):
                        return rel
            prompt = build_ordre_logique_prompt(body)
            data = await call_mistral_ordre_logique_json(prompt)
        else:
            enriched, doc, _from_cache = await _load_or_build_ordre_logique(
                body, force_refresh=force_refresh
            )
            return enriched
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Réponse Mistral non objet JSON")
    return data