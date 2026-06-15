"""Consignes de langue pour la génération de contenu IA (alignée sur la langue UI)."""

from typing import Literal

AppLang = Literal["fr", "en"]


def normalize_lang(lang: str | None) -> AppLang:
    if lang and str(lang).strip().lower().startswith("en"):
        return "en"
    return "fr"


def content_language_block(lang: str | None) -> str:
    """Bloc à injecter en tête des prompts Mistral (texte affiché à l'utilisateur)."""
    if normalize_lang(lang) == "en":
        return """
LANGUAGE (mandatory):
- Write ALL user-facing text in English (labels, taglines, descriptions, analyses, recommendations, exercise text, family titles, etc.).
- Use natural English with correct spelling and capitalization.
- Do NOT use snake_case for display labels; use normal title case or sentence case.
- Technical JSON keys and pyramid level keys (faits_observables, lois_relations, etc.) remain snake_case as specified.
- Keyword arrays for image search must be in English.
"""
    return """
LANGUE (obligatoire) :
- Rédige TOUT le texte affiché à l'utilisateur en français (labels, accroches, descriptions, analyses, recommandations, exercices, titres de familles, etc.).
- Utilise des accents corrects et une orthographe soignée.
- N'utilise PAS le snake_case pour les libellés affichés ; utilise une casse normale (minuscules avec accents, ou majuscule initiale).
- Les clés JSON techniques et les clés de niveau pyramide (faits_observables, lois_relations, etc.) restent en snake_case comme spécifié.
- Les tableaux de mots-clés pour la recherche d'images doivent être en français.
"""


def prompt_prefix(lang: str | None) -> str:
    return content_language_block(lang).strip() + "\n\n"
