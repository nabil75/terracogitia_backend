import json
import os
from typing import Any

import httpx
from mistralai.client import Mistral

from .language_prompts import prompt_prefix, prose_formatting_block


MISTRAL_CHAT_TIMEOUT_MS = int(os.environ.get("MISTRAL_CHAT_TIMEOUT_MS", str(5 * 60 * 1000)))
MISTRAL_DISCOVER_MAX_TOKENS = int(os.environ.get("MISTRAL_DISCOVER_MAX_TOKENS", "8192"))


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


async def call_mistral_ordre_logique_json(prompt: str) -> dict[str, Any]:
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
    except httpx.TimeoutException:
        raise ValueError(
            "L'API Mistral n'a pas répondu dans le délai imparti. Réessayez ou augmentez MISTRAL_CHAT_TIMEOUT_MS (millisecondes)."
        ) from None
    except httpx.HTTPError as e:
        raise ValueError(f"Erreur HTTP lors de l'appel à Mistral : {e!s}") from e
    except Exception as e:
        raise ValueError(f"Erreur lors de l'appel à Mistral : {e!s}") from e
    choices = getattr(chat_response, "choices", None) or []
    if not choices:
        raise ValueError("Réponse Mistral invalide (choices absent).")
    response_text = mistral_message_content_to_text(getattr(choices[0].message, "content", None))
    if not response_text.strip():
        raise ValueError("Réponse Mistral vide.")
    try:
        return parse_json_object_from_llm_content(response_text)
    except Exception as e:
        raise ValueError("Impossible d'extraire ou de valider le JSON renvoyé par Mistral.") from e


async def call_discover_proposition_json(
    subtheme: str,
    question: str,
    lang: str | None = None,
) -> dict[str, Any]:
    api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("Variable d'environnement MISTRAL_API_KEY manquante ou vide.")
    client = Mistral(api_key=api_key, timeout_ms=MISTRAL_CHAT_TIMEOUT_MS)
    prompt = prompt_prefix(lang) + prose_formatting_block(lang) + """

                    Tu es un expert en """+subtheme+""". Ton objectif est de proposer une réponse à la question suivante : """+question+""". 
                    Ta proposition doit être construite sur la base du plan suivant 
                    1. Introduction : Présente brièvement le sujet et son importance.
                    2. Contexte : Fournis un contexte historique ou actuel pour mieux comprendre la question
                    3. Analyse : Analyse les différents aspects de la question, en mettant en évidence les points clés et les enjeux.
                    4. Conclusion : Résume les points principaux et propose une réponse claire à la question.
                    Ta proposition doit inclure des exemples pertinents pour illustrer tes points.
                    IMPORTANT :
                    - Réponds avec du JSON STRICT uniquement.
                    - N'ajoute AUCUN bloc markdown, AUCUN backtick, AUCUN texte avant/après.
                    - Le résultat doit être un OBJET structuré (pas une chaîne).
                    - La clé "Analyse" est OBLIGATOIRE : texte réel, plusieurs phrases, jamais vide ni réduit à "...".
                    - Applique les consignes de MISE EN FORME DU TEXTE ci-dessus dans chaque champ (sauts de ligne et listes numérotées).
                    Fournis ta réponse exactement avec ce format JSON :
                    {
                        "introduction": "..........",
                        "Contexte": "..........",
                        "Analyse": "..........",
                        "Conclusion": ".........."
                    }
                    """
    try:
        chat_response = await client.chat.complete_async(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=MISTRAL_DISCOVER_MAX_TOKENS,
            timeout_ms=MISTRAL_CHAT_TIMEOUT_MS,
        )
    except httpx.TimeoutException:
        raise ValueError(
            "L'API Mistral n'a pas répondu dans le délai imparti. Réessayez ou augmentez MISTRAL_CHAT_TIMEOUT_MS (millisecondes)."
        ) from None
    except httpx.HTTPError as e:
        raise ValueError(f"Erreur HTTP lors de l'appel à Mistral : {e!s}") from e
    except Exception as e:
        raise ValueError(f"Erreur lors de l'appel à Mistral : {e!s}") from e
    choices = getattr(chat_response, "choices", None) or []
    if not choices:
        raise ValueError("Réponse Mistral invalide (choices absent).")
    message = (choices[0] or {}).message
    response_text = mistral_message_content_to_text(getattr(message, "content", None))
    if not response_text or not str(response_text).strip():
        raise ValueError("Réponse Mistral vide.")
    return parse_json_object_from_llm_content(response_text)

