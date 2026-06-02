import json
import os

import httpx

from .theme_mistral import (
    mistral_message_content_to_text,
    parse_json_object_from_llm_content,
)


async def propose_discipline_from_wish_ai(wish: str) -> dict | str:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    prompt = f"""
        Tu es un expert en ingénierie pédagogique pour la plateforme Terra Cogitia.

        Un utilisateur exprime un souhait d'apprentissage (formulation libre, parfois vague ou approximative) :
        « {wish} »

        À partir de ce seul souhait, propose :
        1. **label** : un intitulé court pour la discipline (2 à 6 mots, clair, en français).
        2. **description** : une description pédagogique (2 à 4 phrases) expliquant ce que couvre cette discipline.
        3. Les compétences pratiques développées
        4. Les prérequis éventuels
        5. Un niveau estimé (débutant, intermédiaire, avancé)
        6. Une courte projection concrète de ce que l’apprenant saura faire à la fin

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


async def generate_list_themes_ai(discipline_label: str, discipline_description: str) -> list[dict] | str:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        return "Erreur : variable d'environnement MISTRAL_API_KEY manquante ou vide."
    model = "mistral-large-latest"
    url = "https://api.mistral.ai/v1/chat/completions"
    prompt = """
            Tu es un expert en pédagogie et en structuration de parcours d’apprentissage.
            Ta mission est de définir les principaux thèmes nécessaires pour maîtriser la discipline suivante :
            Nom de la discipline : """ + discipline_label + """
            Description de la discipline : """ + discipline_description + """

            Identifie les grandes transformations cognitives nécessaires pour maîtriser la discipline et associe chacune à un thème d’apprentissage structurant. Privilégie les thèmes qui correspondent à des changements importants dans la manière de comprendre ou de manipuler le domaine.
            Chaque thème doit :
                - représenter une étape importante dans la compréhension du domaine ;
                - contribuer à la montée progressive du concret vers l’abstrait ;
                - pouvoir être exploré selon plusieurs niveaux cognitifs :
                    - faits_observables : observation directe et phénomènes empiriques
                    - lois_relations : règles, mécanismes et causalités
                    - schemes_operatoires : méthodes, procédures et stratégies de résolution
                    - principes_generateurs : invariants conceptuels et idées fondamentales
                    - structures_abstraites : modèles mentaux et organisations globales
                    - metacadres_theoriques : visions intégratrices et limites des modèles

            Pour chaque thème :
                - Fournis un label court (2 à 5 mots maximum)
                - Rédige une phrase d'accroche (tagline) de 10 à 15 mots maximum pour présenter le thème de manière attractive
                - Rédige une description concise (1 à 3 phrases) expliquant les compétences ou connaissances acquises
                - le rôle cognitif principal du thème dans la progression globale : Pourquoi ce thème est-il important dans le parcours d’apprentissage ? Quelle transformation mentale ce thème provoque-t-il ?
                - le niveau dominant de la pyramide concerné : à quel étage de la pyramide (Faits observables, Lois et relations, Schèmes opératoires, Principes générateurs, Structures abstraites, Métacadres théoriques) appartient principalement le savoir étudié.
                - transformation_cognitive : opération mentale dominante (observer|comparer|relier|résoudre|généraliser|modéliser|critiquer|intégrer).

            Les thèmes doivent être :
                - Cohérents avec la description fournie
                - Organisés selon une progression pédagogique logique (du fondamental au plus avancé)
                - Non redondants
                - Suffisamment complets pour couvrir la discipline
                - Chaque thème doit représenter une unité cohérente d’apprentissage pouvant être étudiée indépendamment tout en contribuant à la progression globale.

            Contraintes de sortie :
                - Réponds uniquement en JSON valide. Ne fournis aucun texte en dehors du JSON.
                - Respecte strictement le format suivant (objet racine obligatoire pour le mode JSON du modèle) :
                    {
                        "themes": [
                            {
                                "label": "...",
                                "tagline": "...",
                                "description": "...",
                                "role_cognitif": "...",
                                "niveau_pyramide": "Faits observables|Lois et relations|Schèmes opératoires|Principes générateurs|Structures abstraites|Métacadres théoriques",
                                "transformation_cognitive": "observer|comparer|relier |résoudre| généraliser| modéliser| critiquer|intégrer"
                            }
                        ]
                    }

            """
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

