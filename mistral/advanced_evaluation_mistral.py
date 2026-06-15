"""Prompts Mistral pour l'évaluation avancée (synthèse parcours apprenant)."""

import json
import os
from typing import Any

import httpx

from .language_prompts import normalize_lang, prompt_prefix
from .theme_mistral import mistral_message_content_to_text, parse_json_object_from_llm_content


async def generate_advanced_evaluation_insights(
    overview: dict[str, Any],
    lang: str | None = None,
) -> dict | str:
    """
    Produit une synthèse narrative : acquis, lacunes, effort de découverte,
    croisement avec la pyramide des savoirs.
    """
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."

    overview_json = json.dumps(overview, ensure_ascii=False, indent=2)
    synth_lang = "English" if normalize_lang(lang) == "en" else "French"
    prompt = f"""
{prompt_prefix(lang)}
Tu es un expert en ingénierie pédagogique pour Terra Cogitia.

On te fournit un tableau de bord agrégé (JSON) d'un apprenant :
- scores d'évaluation croisés avec les 6 niveaux de la pyramide des savoirs ;
- points forts / faibles issus des évaluations ;
- effort de découverte (sessions sur parcours, propositions demandées/enregistrées/abandonnées, exercices) ;
- profil cognitive_discovery : opérations cognitives sollicitées en découverte, séquence chronologique,
  opérations jamais explorées, matrice pyramide × opérations, indicateurs (observe-t-il avant de comprendre ?).

{overview_json}

Rédige une synthèse en {synth_lang}, structurée et actionnable :
1. **Transformations mentales observées** — quels niveaux de pyramide sont mobilisés vs négligés.
2. **Acquis solides** — 3 à 6 bullet points concrets.
3. **Points à travailler** — 3 à 6 bullet points priorisés.
4. **Effort de découverte** — commenter l'exploration (temps, parcours visités, propositions).
5. **Conduite cognitive de la découverte** — opérations privilégiées (observer vs comprendre vs modéliser),
   séquence observée, lacunes (opérations disponibles mais jamais sollicitées).
6. **Recommandations** — 2 à 4 pistes concrètes pour la suite.

Reste fidèle aux données ; n'invente pas de scores absents du JSON.

Réponds UNIQUEMENT en JSON valide :
{{
  "transformations_mentales": "...",
  "acquis": ["..."],
  "points_a_travailler": ["..."],
  "effort_decouverte": "...",
  "conduite_decouverte": "...",
  "recommandations": ["..."],
  "commentaire_global": "..."
}}
"""
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code == 400 and body.get("response_format"):
                body = {k: v for k, v in body.items() if k != "response_format"}
                response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return "Erreur : réponse Mistral sans choices."
            message = (choices[0] or {}).get("message") or {}
            text = mistral_message_content_to_text(message.get("content"))
            if not text.strip():
                return "Erreur : réponse Mistral vide."
            return parse_json_object_from_llm_content(text)
    except httpx.HTTPStatusError as e:
        return f"Erreur API Mistral (HTTP {e.response.status_code}) : {(e.response.text or '')[:800]}"
    except Exception as e:
        return f"Erreur : {str(e)}"
