import asyncio
import json
import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException

from .language_prompts import prompt_prefix
from .pyramid_prompts import (
    PYRAMID_CONSTITUTION,
    dominants_from_entity,
    normalize_pyramid_level,
    normalize_pyramid_level_list,
)

logger = logging.getLogger(__name__)

_GENERATE_PARCOURS_TIMEOUT_SEC = float(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_TIMEOUT_SEC", "600")
)
_GENERATE_PARCOURS_MAX_TOKENS = int(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_MAX_TOKENS", "32768")
)
_GENERATE_QUESTIONS_MAX_TOKENS = int(
    os.environ.get("MISTRAL_GENERATE_QUESTIONS_MAX_TOKENS", "16384")
)
_GENERATE_PARCOURS_MAX_RETRIES = int(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_MAX_RETRIES", "4")
)
_GENERATE_PARCOURS_RETRY_BASE_SEC = float(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_RETRY_BASE_SEC", "4")
)
_MISTRAL_RETRYABLE_HTTP = frozenset({429, 502, 503, 504})
MAX_DOMAINES_PER_GENERATION = int(
    os.environ.get("MISTRAL_MAX_DOMAINES_PER_GENERATION", "5")
)
MIN_DOMAINES_PER_GENERATION = int(
    os.environ.get("MISTRAL_MIN_DOMAINES_PER_GENERATION", "4")
)
DEFAULT_QUESTIONS_PER_PARCOURS = int(
    os.environ.get("MISTRAL_DEFAULT_QUESTIONS_PER_PARCOURS", "16")
)


def _httpx_generate_parcours_timeout() -> httpx.Timeout:
    read = max(60.0, _GENERATE_PARCOURS_TIMEOUT_SEC)
    return httpx.Timeout(connect=30.0, read=read, write=60.0, pool=30.0)


async def _post_mistral_chat_with_retries(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> httpx.Response:
    attempts = max(1, _GENERATE_PARCOURS_MAX_RETRIES)
    last: httpx.Response | None = None
    for attempt in range(1, attempts + 1):
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 400 and payload.get("response_format"):
            payload_fallback = {
                k: v for k, v in payload.items() if k != "response_format"
            }
            response = await client.post(url, headers=headers, json=payload_fallback)
        if response.status_code not in _MISTRAL_RETRYABLE_HTTP:
            return response
        last = response
        if attempt >= attempts:
            break
        wait = _GENERATE_PARCOURS_RETRY_BASE_SEC * (2 ** (attempt - 1))
        logger.warning(
            "Mistral HTTP %s (tentative %s/%s), nouvel essai dans %.1fs — %s",
            response.status_code,
            attempt,
            attempts,
            wait,
            (response.text or "")[:240],
        )
        await asyncio.sleep(wait)
    assert last is not None
    return last


def mistral_message_content_to_text(content: Any) -> str:
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


def strip_markdown_json_fence(text: str) -> str:
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


def parse_json_object_from_llm_content(content: str) -> dict:
    text = strip_markdown_json_fence(content)
    start = text.find("{")
    if start == -1:
        raise ValueError("Aucun objet JSON dans la réponse du modèle.")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text, start)
    if not isinstance(obj, dict):
        raise ValueError("Le JSON racine doit être un objet.")
    return obj


def salvage_domaines_from_truncated_llm_json(content: str) -> list[dict]:
    text = strip_markdown_json_fence(content)
    key_idx = text.find('"domaines"')
    if key_idx < 0:
        raise ValueError('Clé "domaines" introuvable dans la réponse.')
    bracket = text.find("[", key_idx)
    if bracket < 0:
        raise ValueError('Tableau "domaines" introuvable.')
    decoder = json.JSONDecoder()
    i = bracket + 1
    domaines: list[dict] = []
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\n\r,":
            i += 1
        if i >= n or text[i] == "]":
            break
        if text[i] != "{":
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            domaines.append(obj)
        i = end
    if not domaines:
        raise ValueError("Aucun domaine JSON complet récupérable.")
    return domaines


def parse_parcours_domaines_from_llm_content(
    content: str,
) -> tuple[list[dict], bool]:
    try:
        root = parse_json_object_from_llm_content(content)
        raw = root.get("domaines") or []
        if not isinstance(raw, list):
            raise ValueError('"domaines" doit être un tableau.')
        domaines = [d for d in raw if isinstance(d, dict)]
        if not domaines:
            raise ValueError("Tableau domaines vide.")
        return domaines, False
    except (ValueError, json.JSONDecodeError):
        return salvage_domaines_from_truncated_llm_json(content), True


def parse_questions_from_llm_content(content: str) -> list[dict]:
    root = parse_json_object_from_llm_content(content)
    raw = root.get("questions") or []
    if not isinstance(raw, list):
        raise ValueError('"questions" doit être un tableau.')
    return [q for q in raw if isinstance(q, dict)]


def parse_regroupement_llm_response_text(content: str) -> dict:
    text = strip_markdown_json_fence((content or "").strip())
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
                return parse_json_object_from_llm_content(content)
        else:
            return parse_json_object_from_llm_content(content)
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
        raise ValueError("JSON tableau non reconnu.")
    if isinstance(parsed, dict):
        return parsed
    raise ValueError("JSON racine doit être un objet ou un tableau.")


async def mistral_regroupe_questions_par_cours(
    questions: list[dict],
    max_familles: int,
) -> dict:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="Variable d'environnement MISTRAL_API_KEY manquante ou vide.")
    questions_json = json.dumps(questions, ensure_ascii=False)
    prompt = (
        "Tu es un expert en pédagogie et en analyse de contenus.\n\n"
        "Voici les questions d'un même parcours d'apprentissage (JSON : id_question, libelle) :\n"
        f"{questions_json}\n\n"
        "Regroupe ces questions en familles homogènes (thème ou type de compétence), en t'appuyant "
        "uniquement sur les libellés des questions. Le NOMBRE de familles n'est pas fixé à l'avance : "
        "choisis-le selon l'homogénéité naturelle des contenus (évite de fusionner des thèmes trop "
        f"différents ; évite aussi d'éclater artificiellement). Limite stricte : au plus {max_familles} "
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
        f'La clé racine obligatoire est "familles". Elle contient entre 1 et {max_familles} objets '
        '(inclus). Chaque objet a obligatoirement les deux clés "libelle" et "id_questions".'
    )
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            payloads = (
                {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                {"model": model, "messages": [{"role": "user", "content": prompt}]},
            )
            last_parse_msg: str | None = None
            for req_payload in payloads:
                response = await client.post(url, headers=headers, json=req_payload)
                if response.status_code == 400 and req_payload.get("response_format"):
                    req_payload = {k: v for k, v in req_payload.items() if k != "response_format"}
                    response = await client.post(url, headers=headers, json=req_payload)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise HTTPException(status_code=502, detail="Réponse Mistral sans choices.")
                message = (choices[0] or {}).get("message") or {}
                response_text = mistral_message_content_to_text(message.get("content"))
                if not response_text.strip():
                    raise HTTPException(status_code=502, detail="Réponse Mistral vide.")
                try:
                    return parse_regroupement_llm_response_text(response_text)
                except ValueError as e:
                    last_parse_msg = str(e)
                    continue
            raise HTTPException(status_code=502, detail=f"Réponse IA illisible ou structure inattendue. {last_parse_msg or ''}".strip())
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        raise HTTPException(status_code=502, detail=f"Erreur API Mistral (HTTP {e.response.status_code}) : {snippet}") from e
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="Timeout de la requête vers Mistral.") from None


def _normalize_existing_domaines_for_prompt(
    existing_domaines: list[dict] | None,
) -> list[dict]:
    if not existing_domaines:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for d in existing_domaines:
        if not isinstance(d, dict):
            continue
        lab = (d.get("label") or d.get("titre") or "").strip()
        if not lab:
            continue
        key = lab.lower()
        if key in seen:
            continue
        seen.add(key)
        dom = dominants_from_entity(d) or (d.get("niveau_pyramide") or "").strip()
        out.append(
            {
                "label": lab,
                "description": (d.get("description") or "").strip(),
                "niveau_pyramide": dom or "",
                "niveau_pyramide_dominant": dom or "",
                "role_cognitif": (d.get("role_cognitif") or "").strip(),
            }
        )
    return out


def _domaines_per_generation_instruction(*, complement: bool) -> str:
    min_d = MIN_DOMAINES_PER_GENERATION
    max_d = MAX_DOMAINES_PER_GENERATION
    if min_d > max_d:
        min_d, max_d = max_d, min_d
    if complement:
        return (
            f"- Pour CET APPEL uniquement, génère entre {min_d} et {max_d} NOUVEAUX parcours "
            f'(jamais plus de {max_d} dans le tableau "domaines" de cette réponse), '
            "en complément des parcours déjà listés."
        )
    return (
        f"- Pour CET APPEL uniquement, génère entre {min_d} et {max_d} parcours "
        f'(jamais plus de {max_d} dans le tableau "domaines" de cette réponse).'
    )


def _default_profil_questions(dominant: str | None, total: int = DEFAULT_QUESTIONS_PER_PARCOURS) -> dict:
    rep = {level: 0 for level in (
        "faits_observables",
        "lois_relations",
        "schemes_operatoires",
        "principes_generateurs",
        "structures_abstraites",
        "metacadres_theoriques",
    )}
    dom = dominant or "faits_observables"
    rep[dom] = max(1, int(total * 0.4))
    remaining = total - rep[dom]
    order = list(rep.keys())
    idx = order.index(dom) if dom in order else 0
    for level in order[idx + 1 :]:
        if remaining <= 0:
            break
        take = min(remaining, max(1, remaining // 2))
        rep[level] = take
        remaining -= take
    if remaining > 0:
        rep[dom] += remaining
    return {"repartition": rep, "total": total}


def _normalize_parcours_domaine(dom: dict) -> dict:
    """Normalise un domaine IA (parcours) vers les clés persistées."""
    dominant = dominants_from_entity(dom)
    secondaires = normalize_pyramid_level_list(dom.get("niveaux_secondaires"))
    profil = dom.get("profil_questions_attendu")
    if not isinstance(profil, dict):
        profil = _default_profil_questions(dominant)
    rep = profil.get("repartition")
    if not isinstance(rep, dict):
        profil = _default_profil_questions(dominant)
    return {
        **dom,
        "label": (dom.get("label") or dom.get("titre") or "").strip(),
        "description": (dom.get("description") or "").strip(),
        "niveau_pyramide": dominant,
        "niveau_pyramide_dominant": dominant,
        "niveaux_secondaires": secondaires,
        "profil_questions_attendu": profil,
    }


def _normalize_question_entry(q: dict) -> dict:
    niveau = normalize_pyramid_level(
        q.get("niveau_pyramide") or q.get("niveau_cognitif")
    )
    return {
        "libelle": (q.get("libelle") or q.get("label") or "").strip(),
        "niveau_pyramide": niveau,
        "niveau_cognitif": (q.get("operation_cognitive") or q.get("niveau_cognitif") or "").strip() or None,
        "operation_cognitive": (q.get("operation_cognitive") or "").strip() or None,
        "objectif_pedagogique": (q.get("objectif_pedagogique") or "").strip() or None,
        "concepts_vises": q.get("concepts_vises") if isinstance(q.get("concepts_vises"), list) else [],
        "prerequis_concepts": q.get("prerequis_concepts") if isinstance(q.get("prerequis_concepts"), list) else [],
    }


def _build_parcours_generation_prompt(
    context: str,
    existing_domaines: list[dict] | None,
    theme_meta: dict | None = None,
    lang: str | None = None,
) -> str:
    existing = _normalize_existing_domaines_for_prompt(existing_domaines)
    meta = theme_meta or {}

    if existing:
        existing_json = json.dumps(existing, ensure_ascii=False, indent=2)
        count_line = _domaines_per_generation_instruction(complement=True)
        existing_block = f"""
Parcours DÉJÀ présents pour ce thème — à ne PAS dupliquer. Ne les inclus PAS dans "domaines" :
{existing_json}

{count_line}
- Les nouveaux parcours doivent être complémentaires, couvrir d'autres angles de la pyramide,
  et éviter toute redondance sémantique avec les libellés ci-dessus.
"""
    else:
        existing_block = _domaines_per_generation_instruction(complement=False)

    theme_niveau = dominants_from_entity(meta) or meta.get("niveau_pyramide") or "non précisé"
    theme_role = (meta.get("role_cognitif") or "").strip() or "non précisé"
    theme_transfo = (meta.get("transformation_cognitive") or "").strip() or "non précisé"

    return f"""
        {prompt_prefix(lang)}
        Tu es un architecte de parcours d'apprentissage pour Terra Cogitia.

        {PYRAMID_CONSTITUTION}

        THÈME PARENT (contexte) :
        {context}

        Métadonnées du thème parent :
        - niveau_pyramide_dominant : {theme_niveau}
        - role_cognitif : {theme_role}
        - transformation_cognitive : {theme_transfo}

        {existing_block}

        OBJECTIF :
        Générer des parcours (sous-thèmes) qui découpent le thème en unités d'apprentissage autonomes mais ordonnées.

        RÈGLE CENTRALE :
        Chaque parcours est ANCRÉ sur UN niveau_pyramide_dominant (clé snake_case exacte). L'ensemble des parcours :
        - couvre le niveau dominant du thème parent ET au moins un niveau adjacent ;
        - est ordonné du plus concret au plus abstrait ;
        - évite deux parcours avec le même niveau_pyramide_dominant ET le même role_cognitif.

        Pour CHAQUE parcours (dans "domaines", SANS questions — elles seront générées séparément) :
        - label : court, évocateur, orienté transformation
        - description : max 2 phrases
        - niveau_pyramide_dominant : clé snake_case
        - niveaux_secondaires : 0 à 2 clés
        - role_cognitif : une phrase
        - transformations_cognitives : 2 à 4 verbes courts
        - prerequis : labels de parcours antérieurs
        - ouvre_vers : labels de parcours suivants
        - profil_questions_attendu : objet avec repartition (6 clés snake_case, entiers) et total (16 à 20)

        profil_questions_attendu :
        - total entre 16 et 20
        - le niveau_pyramide_dominant du parcours reçoit au moins 40 % des questions
        - au moins 2 niveaux différents par parcours
        - si niveau_pyramide_dominant >= principes_generateurs : au moins 1 question aux niveaux 5 ou 6

        ANTI-PATTERNS : parcours encyclopédiques sans ancrage pyramide ; pas de tableau "questions" dans cette réponse.

        Réponds UNIQUEMENT en JSON valide :

        {{
        "domaines": [
            {{
            "label": "",
            "description": "",
            "niveau_pyramide_dominant": "faits_observables",
            "niveaux_secondaires": [],
            "role_cognitif": "",
            "transformations_cognitives": [],
            "prerequis": [],
            "ouvre_vers": [],
            "profil_questions_attendu": {{
                "repartition": {{
                "faits_observables": 0,
                "lois_relations": 0,
                "schemes_operatoires": 0,
                "principes_generateurs": 0,
                "structures_abstraites": 0,
                "metacadres_theoriques": 0
                }},
                "total": 16
            }}
            }}
        ],
        "controle_pyramide": {{
            "niveaux_couverts": [],
            "ordre_respecte": true
        }}
        }}
    """


def _build_questions_generation_prompt(parcours: dict, lang: str | None = None) -> str:
    parcours = _normalize_parcours_domaine(parcours)
    label = parcours.get("label") or "Parcours"
    desc = parcours.get("description") or ""
    dominant = parcours.get("niveau_pyramide_dominant") or "faits_observables"
    role = parcours.get("role_cognitif") or ""
    transfo = parcours.get("transformations_cognitives") or []
    profil = parcours.get("profil_questions_attendu") or _default_profil_questions(dominant)
    total = int(profil.get("total") or DEFAULT_QUESTIONS_PER_PARCOURS)
    total = max(12, min(20, total))
    repartition = profil.get("repartition") or _default_profil_questions(dominant, total)["repartition"]
    repartition_json = json.dumps(repartition, ensure_ascii=False)

    return f"""
{prompt_prefix(lang)}
Tu es un concepteur de questions pour Terra Cogitia. Tu produis des questions qui TESTENT et ENTRAÎNENT un niveau précis de la pyramide des savoirs.

{PYRAMID_CONSTITUTION}

PARCOURS :
- label : {label}
- description : {desc}
- niveau_pyramide_dominant : {dominant}
- role_cognitif : {role}
- transformations_cognitives : {json.dumps(transfo, ensure_ascii=False)}

PROFIL CIBLE (répartition obligatoire, total = {total}) :
{repartition_json}

CALIBRAGE PAR NIVEAU (respecter niveau_pyramide de chaque question) :
| niveau_pyramide          | types autorisés                          | verbes typiques                            |
| faits_observables        | constat, observation, exemple concret    | observer, décrire, identifier, reconnaître |
| lois_relations           | causalité, comparaison, prédiction       | expliquer pourquoi, relier, comparer       |
| schemes_operatoires      | procédure, méthode, résolution           | appliquer, choisir, exécuter, corriger     |
| principes_generateurs    | généralisation, invariant, transfert     | généraliser, unifier, transférer           |
| structures_abstraites    | modélisation, schéma, architecture       | modéliser, structurer, représenter         |
| metacadres_theoriques    | critique de modèle, limites, cadres      | critiquer, comparer des cadres, intégrer   |

RÈGLES :
1. Exactement {total} questions, répartition conforme au profil (±1 max sur un niveau, compensé ailleurs).
2. Ordre : majoritairement du plus concret vers le plus abstrait du profil.
3. Chaque question : libelle (max 25 mots), niveau_pyramide (clé exacte), operation_cognitive (un verbe), objectif_pedagogique (max 15 mots), concepts_vises (2 à 4), prerequis_concepts (0 à 3).
4. Au moins 40 % des questions au niveau_pyramide_dominant du parcours ({dominant}).

Réponds UNIQUEMENT en JSON valide :

{{
  "id_parcours_label": "{label}",
  "questions": [
    {{
      "libelle": "",
      "niveau_pyramide": "",
      "operation_cognitive": "",
      "objectif_pedagogique": "",
      "concepts_vises": [],
      "prerequis_concepts": []
    }}
  ],
  "controle_pyramide": {{
    "repartition_obtenue": {{}},
    "conforme_profil": true
  }}
}}
"""


async def _call_mistral_json(
    prompt: str,
    *,
    max_tokens: int,
    parse_fn,
) -> Any:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    client_timeout = _httpx_generate_parcours_timeout()
    try:
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            response = await _post_mistral_chat_with_retries(
                client, url, headers, payload
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return f"Erreur : réponse Mistral sans choices. Réponse : {str(data)[:800]}"
            message = (choices[0] or {}).get("message") or {}
            response_text = mistral_message_content_to_text(message.get("content"))
            if not response_text.strip():
                return f"Erreur : pas de contenu dans la réponse. Réponse : {str(data)[:800]}"
            finish_reason = (choices[0] or {}).get("finish_reason") or ""
            try:
                return parse_fn(response_text, finish_reason)
            except (ValueError, json.JSONDecodeError) as parse_err:
                if finish_reason == "length":
                    return (
                        "Erreur : réponse Mistral tronquée (limite de tokens). "
                        f"Détail : {parse_err}."
                    )
                return f"Erreur : impossible d'extraire le JSON ({parse_err})."
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        status = e.response.status_code
        extra = ""
        if status in _MISTRAL_RETRYABLE_HTTP:
            extra = f" ({_GENERATE_PARCOURS_MAX_RETRIES} tentatives avec backoff)."
        return f"Erreur API Mistral (HTTP {status}) : {snippet}{extra}"
    except httpx.TimeoutException:
        return (
            "Erreur : timeout de la requête vers Mistral (délai dépassé). "
            f"Délai actuel : {_GENERATE_PARCOURS_TIMEOUT_SEC:.0f} s."
        )
    except Exception as e:
        return f"Erreur : {str(e)}"


def _parse_parcours_response(response_text: str, finish_reason: str) -> tuple[list[dict], bool, dict]:
    domaines, partial = parse_parcours_domaines_from_llm_content(response_text)
    domaines = [_normalize_parcours_domaine(d) for d in domaines]
    try:
        root = parse_json_object_from_llm_content(response_text)
    except (ValueError, json.JSONDecodeError):
        root = {}
    partial = partial or finish_reason == "length"
    return domaines, partial, root


def _parse_questions_response(response_text: str, finish_reason: str) -> list[dict]:
    questions = parse_questions_from_llm_content(response_text)
    if finish_reason == "length" and not questions:
        raise ValueError("Réponse tronquée sans question récupérable.")
    return [_normalize_question_entry(q) for q in questions if _normalize_question_entry(q).get("libelle")]


async def generate_parcours_ai(
    context: str,
    existing_domaines: list[dict] | None = None,
    theme_meta: dict | None = None,
    lang: str | None = None,
) -> dict | str:
    """Génère uniquement les parcours (domaines), sans questions."""
    prompt = _build_parcours_generation_prompt(
        context, existing_domaines, theme_meta, lang
    )
    result = await _call_mistral_json(
        prompt,
        max_tokens=_GENERATE_PARCOURS_MAX_TOKENS,
        parse_fn=_parse_parcours_response,
    )
    if isinstance(result, str):
        return result
    domaines, partial, root = result
    return {
        "label": (root.get("titre") or root.get("label") or "").strip(),
        "tagline": (root.get("accroche") or root.get("tagline") or "").strip(),
        "description": (root.get("description") or "").strip(),
        "domaines": domaines,
        "partial": partial,
    }


async def generate_questions_for_parcours_ai(
    parcours: dict,
    lang: str | None = None,
) -> list[dict] | str:
    """Génère les questions pour un parcours déjà défini (appel Mistral séparé)."""
    prompt = _build_questions_generation_prompt(parcours, lang)
    result = await _call_mistral_json(
        prompt,
        max_tokens=_GENERATE_QUESTIONS_MAX_TOKENS,
        parse_fn=lambda text, fr: _parse_questions_response(text, fr),
    )
    if isinstance(result, str):
        return result
    return result


async def generate_theme_ai(
    context: str,
    existing_domaines: list[dict] | None = None,
    theme_meta: dict | None = None,
    lang: str | None = None,
) -> dict | str:
    """
    Orchestre : 1) génération des parcours, 2) génération des questions par parcours (appels séparés).
  """
    parcours_result = await generate_parcours_ai(
        context,
        existing_domaines=existing_domaines,
        theme_meta=theme_meta,
        lang=lang,
    )
    if isinstance(parcours_result, str):
        return parcours_result

    domaines = parcours_result.get("domaines") or []
    partial = parcours_result.get("partial", False)

    for dom in domaines:
        if dom.get("questions"):
            continue
        q_result = await generate_questions_for_parcours_ai(dom, lang)
        if isinstance(q_result, str):
            logger.warning(
                "Questions non générées pour parcours %r : %s",
                dom.get("label"),
                q_result[:200],
            )
            dom["questions"] = []
            partial = True
        else:
            dom["questions"] = q_result

    return {
        "label": parcours_result.get("label") or "",
        "tagline": parcours_result.get("tagline") or "",
        "description": parcours_result.get("description") or "",
        "domaines": domaines,
        "partial": partial,
    }
