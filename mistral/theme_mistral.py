import asyncio
import json
import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Génération parcours + questions (JSON volumineux) : délai lecture HTTP plus long que le reste.
_GENERATE_PARCOURS_TIMEOUT_SEC = float(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_TIMEOUT_SEC", "600")
)
# JSON volumineux : 32k évite la coupure « Unterminated string » observée vers ~68k caractères.
_GENERATE_PARCOURS_MAX_TOKENS = int(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_MAX_TOKENS", "32768")
)
_GENERATE_PARCOURS_MAX_RETRIES = int(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_MAX_RETRIES", "4")
)
_GENERATE_PARCOURS_RETRY_BASE_SEC = float(
    os.environ.get("MISTRAL_GENERATE_PARCOURS_RETRY_BASE_SEC", "4")
)
_MISTRAL_RETRYABLE_HTTP = frozenset({429, 502, 503, 504})
# Limite par appel Mistral uniquement (pas de plafond sur le nombre total de parcours d'un thème).
MAX_DOMAINES_PER_GENERATION = int(
    os.environ.get("MISTRAL_MAX_DOMAINES_PER_GENERATION", "5")
)
MIN_DOMAINES_PER_GENERATION = int(
    os.environ.get("MISTRAL_MIN_DOMAINES_PER_GENERATION", "4")
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
    """Réessaie les erreurs transitoires Mistral (503 unreachable_backend, 429, 502, 504)."""
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
    """
    Si le JSON est coupé (max_tokens), récupère les objets « domaine » déjà complets
    dans le tableau ``domaines``.
    """
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
    """
    Retourne (domaines, partial).
    ``partial=True`` si le JSON racine était tronqué mais des domaines complets ont été sauvés.
    """
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
        out.append(
            {
                "label": lab,
                "description": (d.get("description") or "").strip(),
                "niveau_pyramide": (d.get("niveau_pyramide") or "").strip(),
                "role_cognitif": (d.get("role_cognitif") or "").strip(),
            }
        )
    return out


def _domaines_per_generation_instruction(*, complement: bool) -> str:
    """Consigne de volume pour un seul appel de génération (pas un plafond cumulé sur le thème)."""
    min_d = MIN_DOMAINES_PER_GENERATION
    max_d = MAX_DOMAINES_PER_GENERATION
    if min_d > max_d:
        min_d, max_d = max_d, min_d
    if complement:
        return (
            f"- Pour CET APPEL uniquement, génère entre {min_d} et {max_d} NOUVEAUX sous-thèmes "
            f"cognitifs (jamais plus de {max_d} dans le tableau \"domaines\" de cette réponse), "
            "en complément des parcours déjà listés. Le thème peut compter plus de parcours "
            "au fil de plusieurs générations successives."
        )
    return (
        f"- Pour CET APPEL uniquement, génère entre {min_d} et {max_d} sous-thèmes cognitifs "
        f"(jamais plus de {max_d} dans le tableau \"domaines\" de cette réponse)."
    )


def _build_parcours_generation_prompt(
    context: str,
    existing_domaines: list[dict] | None,
) -> str:
    existing = _normalize_existing_domaines_for_prompt(existing_domaines)

    if existing:
        existing_json = json.dumps(existing, ensure_ascii=False, indent=2)
        count_line = _domaines_per_generation_instruction(complement=True)
        existing_block = f"""
        Parcours (domaines) DÉJÀ présents pour ce thème — à ne PAS dupliquer ni reformuler à l'identique.
        Ne les inclus PAS dans le tableau \"domaines\" de ta réponse :
        {existing_json}

        {count_line}
        - Les nouveaux domaines doivent être complémentaires, couvrir d'autres angles de la pyramide des savoirs,
          et éviter toute redondance sémantique avec les libellés ci-dessus.
        """
    else:
        existing_block = _domaines_per_generation_instruction(complement=False)

    return f"""
        Tu es un architecte pédagogique spécialisé en cognition computationnelle, systèmes tutoriels intelligents et graphes de connaissances.

        Ta mission est de transformer un thème de savoir en une architecture cognitive d'apprentissage structurée.

        Entrée (label, accroche et description du thème) :
        {context}

        Objectif :
        Construire un arbre de progression pédagogique permettant à un apprenant de maîtriser progressivement le thème en traversant différents niveaux d'abstraction selon la pyramide des savoirs.

        La pyramide des savoirs comporte les niveaux suivants :

        1. faits_observables : phénomènes directement observables, expériences, constats empiriques
        2. lois_relations : règles, mécanismes, causalités et relations entre les phénomènes
        3. schemes_operatoires : méthodes, procédures, stratégies et façons de résoudre des problèmes
        4. principes_generateurs : idées fondamentales, invariants conceptuels, mécanismes profonds expliquant plusieurs méthodes
        5. structures_abstraites : modèles mentaux, architectures conceptuelles, représentations globales du domaine
        6. metacadres_theoriques : visions globales, limites des modèles, cadres interprétatifs et liens interdisciplinaires

        Instructions :
        {existing_block}
        - Chaque sous-thème doit représenter une transformation cognitive importante dans la maîtrise du thème.
        - Organise les sous-thèmes selon une progression allant du concret vers l'abstrait.
        - Évite les découpages encyclopédiques classiques.
        - Chaque sous-thème (domaine) doit pouvoir être étudié indépendamment tout en contribuant à la progression globale.

        Pour chaque NOUVEAU sous-thème, génère :
        - un label court et évocateur
        - une description concise, au plus 2 phrases
        - le niveau dominant de la pyramide auquel le sous-thème peut être rattaché
        - le rôle cognitif du sous-thème
        - les transformations cognitives principales
        - les prérequis éventuels (tu peux référencer des labels de parcours existants)
        - les sous-thèmes suivants qu'il permet d'ouvrir
        - entre 16 et 20 questions progressives par sous-thème (jamais plus de 20), avec des types cognitifs variés et des objectifs pédagogiques clairs.

        Contraintes de concision (obligatoires pour tenir en un seul JSON) :
        - libellé de question : 25 mots maximum
        - objectif_pedagogique : 15 mots maximum
        - concepts_vises : 2 à 4 entrées courtes maximum
        - transformations_cognitives, prerequis, ouvre_vers : libellés courts, 4 éléments maximum chacun

        Les questions doivent favoriser le raisonnement, la montée en abstraction et l'esprit critique.

        Chaque question doit contenir : libelle, niveau_cognitif, objectif_pedagogique, concepts_vises.

        Réponds uniquement en JSON valide.

        Respecte STRICTEMENT la structure suivante (uniquement les NOUVEAUX domaines dans \"domaines\") :

        {{
        "domaines": [
            {{
            "label": "",
            "description": "",
            "niveau_pyramide": "",
            "role_cognitif": "",
            "transformations_cognitives": [],
            "prerequis": [],
            "ouvre_vers": [],
            "questions": [
                {{
                "libelle": "",
                "niveau_cognitif": "",
                "objectif_pedagogique": "",
                "concepts_vises": []
                }}
            ]
            }}
        ]
        }}
    """


async def generate_theme_ai(
    context: str,
    existing_domaines: list[dict] | None = None,
) -> dict | str:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    # prompt = """
    #     Génère un thème d'apprentissage original et structuré sur """ + context + """. Le thème doit comporter 8 à 10 piliers de savoir (domaines) couvrant les aspects techniques, théoriques, applicatifs, éthiques et historiques. Chaque domaine doit être formulé de manière à susciter la curiosité et à permettre une exploration approfondie et suivi d'environ 20 questions pour évaluer la connaissance de l'apprenant.
    #     Les résultats devront se présenter sous la forme d'un fichier JSON strict (aucun texte hors du JSON) au format suivant :
    #     {
    #         "titre" : ".....",
    #         "accroche" : "......",
    #         "description" : ".......",
    #         "domaines" :
    #             [
    #                 {
    #                 "titre" : "......",
    #                 "description" : ".......",
    #                 "questions" :
    #                     [
    #                         "Texte de la question 1",
    #                         "Texte de la question 2"
    #                     ]
    #                 }
    #             ]
    #     }
    #     Le titre du thème et de chaque domaine doit être concis et évocateur. L'accroche du thème est une phrase accrocheuse ; les descriptions font au plus 2 phrases. Les questions évaluent la compréhension des concepts du domaine. Utilise obligatoirement les clés "titre", "accroche", "description", "domaines", et dans chaque domaine "titre", "description", "questions" (tableau de chaînes).
    # """
    prompt = _build_parcours_generation_prompt(context, existing_domaines)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": _GENERATE_PARCOURS_MAX_TOKENS,
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
                domaines, partial = parse_parcours_domaines_from_llm_content(
                    response_text
                )
            except (ValueError, json.JSONDecodeError) as parse_err:
                if finish_reason == "length":
                    return (
                        "Erreur : réponse Mistral tronquée (limite de tokens). "
                        f"Détail : {parse_err}. "
                        "Réduisez le volume ou augmentez MISTRAL_GENERATE_PARCOURS_MAX_TOKENS."
                    )
                return f"Erreur : impossible d'extraire le JSON ({parse_err})."
            if partial or finish_reason == "length":
                logger.warning(
                    "Génération parcours : JSON partiel — %s domaine(s) récupéré(s), finish_reason=%s",
                    len(domaines),
                    finish_reason,
                )
            try:
                response_json = parse_json_object_from_llm_content(response_text)
            except (ValueError, json.JSONDecodeError):
                response_json = {}
            return {
                "label": (
                    response_json.get("titre") or response_json.get("label") or ""
                ).strip(),
                "tagline": (
                    response_json.get("accroche") or response_json.get("tagline") or ""
                ).strip(),
                "description": (response_json.get("description") or "").strip(),
                "domaines": domaines,
                "partial": partial or finish_reason == "length",
            }
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        status = e.response.status_code
        extra = ""
        if status in _MISTRAL_RETRYABLE_HTTP:
            extra = (
                f" ({_GENERATE_PARCOURS_MAX_RETRIES} tentatives avec backoff). "
                "Erreur souvent transitoire côté Mistral : réessayez dans quelques minutes. "
                "Si cela persiste, réduisez le volume demandé dans le prompt ou "
                "MISTRAL_GENERATE_PARCOURS_MAX_TOKENS."
            )
        return f"Erreur API Mistral (HTTP {status}) : {snippet}{extra}"
    except httpx.TimeoutException:
        return (
            "Erreur : timeout de la requête vers Mistral (délai dépassé). "
            f"Délai actuel : {_GENERATE_PARCOURS_TIMEOUT_SEC:.0f} s "
            "(variable d'environnement MISTRAL_GENERATE_PARCOURS_TIMEOUT_SEC)."
        )
    except Exception as e:
        return f"Erreur : {str(e)}"

