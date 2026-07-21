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
- Write ALL user-facing text in English (labels, taglines, descriptions, analyses, recommendations, family titles, etc.).
- Use natural English with correct spelling and capitalization.
- Do NOT use snake_case for display labels; use normal title case or sentence case.
- Technical JSON keys and pyramid level keys (faits_observables, lois_relations, etc.) remain snake_case as specified.
"""
    return """
LANGUE (obligatoire) :
- Rédige TOUT le texte affiché à l'utilisateur en français (labels, accroches, descriptions, analyses, recommandations, titres de familles, etc.).
- Utilise des accents corrects et une orthographe soignée.
- N'utilise PAS le snake_case pour les libellés affichés ; utilise une casse normale (minuscules avec accents, ou majuscule initiale).
- Les clés JSON techniques et les clés de niveau pyramide (faits_observables, lois_relations, etc.) restent en snake_case comme spécifié.
"""


def prompt_prefix(lang: str | None) -> str:
    return content_language_block(lang).strip() + "\n\n"


def prose_formatting_block(lang: str | None) -> str:
    """Consignes de mise en forme du texte dans les champs JSON (retours à la ligne, listes)."""
    if normalize_lang(lang) == "en":
        return """
TEXT FORMATTING (inside each JSON field: introduction, Contexte, Analyse, Conclusion):
- Separate each distinct idea with a blank line (double newline \\n\\n).
- For enumerations, put each item on its own line with a numeric prefix: "1. ", "2. ", "3. ", etc.
- For bullet lists, use the prefix "- " at the start of each line.
- Do not cram several numbered points into one long sentence; prefer a clear numbered list.
- Keep flowing prose for narrative paragraphs; use lists only when listing options, steps, or factors.
""".strip()
    return """
MISE EN FORME DU TEXTE (dans chaque champ JSON : introduction, Contexte, Analyse, Conclusion) :
- Sépare chaque idée distincte par une ligne vide (double saut de ligne \\n\\n).
- Pour une énumération, place chaque élément sur sa propre ligne avec un préfixe numérique : « 1. », « 2. », « 3. », etc.
- Pour une liste à puces, utilise le préfixe « - » au début de chaque ligne.
- N'entasse pas plusieurs points numérotés dans une seule phrase ; privilégie une liste numérotée lisible.
- Garde un texte narratif fluide pour les paragraphes ; utilise des listes lorsque tu énumères des options, étapes ou facteurs.
""".strip()
