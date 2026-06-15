import json
import os

import httpx

from .language_prompts import normalize_lang, prompt_prefix
from .pyramid_prompts import PYRAMID_CONSTITUTION
from .theme_mistral import (
    mistral_message_content_to_text,
    parse_json_object_from_llm_content,
)


async def propose_discipline_from_wish_ai(wish: str, lang: str | None = None) -> dict | str:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    lang = normalize_lang(lang)
    label_lang = "English" if lang == "en" else "French"
    prompt = f"""
        {prompt_prefix(lang)}
        Tu es un expert en ingénierie pédagogique pour la plateforme Terra Cogitia.

        Un utilisateur exprime un souhait d'apprentissage (formulation libre, parfois vague ou approximative) :
        « {wish} »

        À partir de ce seul souhait, propose :
        1. **label** : un intitulé court pour la discipline (2 à 6 mots, clair, en {label_lang}).
        2. **description** : une description pédagogique (2 à 4 phrases) expliquant ce que couvre cette discipline.
        3. Les compétences pratiques développées
        4. Les prérequis éventuels
        5. Un niveau estimé (débutant, intermédiaire, avancé)
        6. Une courte projection concrète de ce que l'apprenant saura faire à la fin

        Reste fidèle à l'intention du souhait ; n'invente pas un domaine sans lien.
        Réponds uniquement en JSON valide, sans texte hors JSON :
        {{
        "label": "...",
        "description": "...",
        "competences": ["compétence 1", "compétence 2"],
        "prerequis": ["prérequis 1", "prérequis 2"],
        "niveau_estime": "debutant|intermediaire|avance",
        "projection": "..."
        }}
        """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code == 400 and body.get("response_format"):
                body_fallback = {k: v for k, v in body.items() if k != "response_format"}
                response = await client.post(url, headers=headers, json=body_fallback)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return f"Erreur : réponse Mistral sans choices. Réponse : {str(data)[:800]}"
            message = (choices[0] or {}).get("message") or {}
            response_text = mistral_message_content_to_text(message.get("content"))
            if not response_text.strip():
                return "Erreur : pas de contenu dans la réponse Mistral."
            return parse_json_object_from_llm_content(response_text)
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        return f"Erreur API Mistral (HTTP {e.response.status_code}) : {snippet}"
    except (ValueError, json.JSONDecodeError) as e:
        return f"Erreur : impossible d'extraire le JSON ({str(e)})."
    except httpx.TimeoutException:
        return "Erreur : timeout de la requête vers Mistral (délai dépassé)."
    except Exception as e:
        return f"Erreur : {str(e)}"


def _build_list_themes_prompt(
    discipline_label: str,
    discipline_description: str,
    lang: str | None = None,
) -> str:
    return f"""
        {prompt_prefix(lang)}
        Tu es un architecte pédagogique pour Terra Cogitia. Ta mission est de découper une discipline en thèmes d'apprentissage qui matérialisent une PROGRESSION EXPLICITE sur la pyramide des savoirs.

        {PYRAMID_CONSTITUTION}

        DISCIPLINE :
        - label : {discipline_label}
        - description : {discipline_description}

        OBJECTIF :
        Produire entre 6 et 10 thèmes (ajuster au périmètre réel de la discipline) tels que :
        1. L'ensemble des thèmes couvre au minimum les niveaux 1 à 4 ; viser 1 à 6 si la discipline le permet.
        2. Le tableau "themes" est ORDONNÉ du plus concret (faits_observables) au plus abstrait (metacadres_theoriques), avec montée progressive — pas un catalogue encyclopédique.
        3. Chaque thème = une transformation cognitive majeure, pas un chapitre de manuel.

        Pour CHAQUE thème, fournir :
        - label : 2 à 5 mots
        - tagline : 10 à 15 mots, accrocheuse
        - description : 1 à 3 phrases (compétences / savoirs visés)
        - niveau_pyramide_dominant : une des 6 clés snake_case
        - niveaux_secondaires : 0 à 2 clés (niveaux touchés mais non dominants)
        - role_cognitif : phrase courte — quelle transformation mentale ce thème provoque
        - transformation_cognitive : une parmi observer|comparer|relier|resoudre|generaliser|modeliser|critiquer|integrer
        - prerequis_themes : labels de thèmes antérieurs dans CE tableau (vide pour le premier)
        - ouvre_themes : labels de thèmes suivants rendus accessibles

        CONTRAINTES DE COUVERTURE (obligatoires) :
        - Au moins 1 thème avec niveau_pyramide_dominant = faits_observables
        - Au moins 1 thème avec niveau_pyramide_dominant ∈ {{principes_generateurs, structures_abstraites, metacadres_theoriques}} si la discipline n'est pas purement procédurale
        - Aucun niveau_pyramide_dominant ne doit apparaître plus de 2 fois (éviter la redondance)
        - Pas de thème dont le niveau dominant est STRICTEMENT inférieur à celui d'un thème listé APRÈS lui (respect de l'ordre)

        ANTI-PATTERNS INTERDITS :
        - Thèmes du type "Introduction", "Historique", "Miscellaneous", "Outils" sans ancrage pyramide
        - Thèmes redondants (même niveau + même rôle cognitif)
        - Thèmes purement encyclopédiques sans transformation cognitive identifiable

        Réponds UNIQUEMENT en JSON valide :

        {{
        "themes": [
            {{
            "label": "",
            "tagline": "",
            "description": "",
            "niveau_pyramide_dominant": "faits_observables",
            "niveaux_secondaires": [],
            "role_cognitif": "",
            "transformation_cognitive": "observer",
            "prerequis_themes": [],
            "ouvre_themes": []
            }}
        ],
        "controle_pyramide": {{
            "niveaux_couverts": ["faits_observables"],
            "ordre_respecte": true,
            "commentaire": ""
        }}
        }}
    """


async def generate_list_themes_ai(
    discipline_label: str,
    discipline_description: str,
    lang: str | None = None,
) -> list[dict] | str:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    prompt = _build_list_themes_prompt(discipline_label, discipline_description, lang)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 400 and payload.get("response_format"):
                payload_fallback = {k: v for k, v in payload.items() if k != "response_format"}
                response = await client.post(url, headers=headers, json=payload_fallback)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return f"Erreur : réponse Mistral sans choices. Réponse : {str(data)[:800]}"
            message = (choices[0] or {}).get("message") or {}
            response_text = mistral_message_content_to_text(message.get("content"))
            if not response_text.strip():
                return f"Erreur : pas de contenu dans la réponse. Réponse : {str(data)[:800]}"
            response_json = parse_json_object_from_llm_content(response_text)
            themes_raw = response_json.get("themes")
            if not isinstance(themes_raw, list):
                return 'Erreur : le JSON doit contenir une clé "themes" avec un tableau.'
            return [item for item in themes_raw if isinstance(item, dict)]
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:1200]
        return f"Erreur API Mistral (HTTP {e.response.status_code}) : {snippet}"
    except (ValueError, json.JSONDecodeError) as e:
        return f"Erreur : impossible d'extraire le JSON ({str(e)})."
    except httpx.TimeoutException:
        return "Erreur : timeout de la requête vers Mistral (délai dépassé)."
    except Exception as e:
        return f"Erreur : {str(e)}"
