# Internationalization Specification

## Purpose
Génération de contenu bilingue (français / anglais) par le LLM Mistral selon la langue
UI courante. Le choix de langue est transmis par les endpoints via un champ optionnel
`lang` ("fr" | "en"), normalisé et injecté en préambule des prompts.

Fichier central : `mistral/language_prompts.py` (`normalize_lang`,
`content_language_block`, `prompt_prefix`).

## Requirements

### Requirement: Normalisation de la langue
Le système SHALL normaliser toute valeur de langue reçue vers `"fr"` ou `"en"`,
en retenant `"en"` uniquement lorsque la valeur commence par `"en"`, et en appliquant
le **français par défaut** dans tous les autres cas (valeur absente, nulle ou inconnue).

#### Scenario: Valeur anglaise
- GIVEN un paramètre `lang` valant `"en"`, `"en-US"` ou `"English"`
- WHEN la langue est normalisée
- THEN le résultat est `"en"`

#### Scenario: Valeur absente ou inconnue
- GIVEN un `lang` absent, nul, `"fr"`, ou une valeur non reconnue
- WHEN la langue est normalisée
- THEN le résultat est `"fr"`

### Requirement: Préambule de langue dans les prompts
Le système SHALL préfixer les prompts de génération IA par un bloc de langue imposant
que **tout le texte destiné à l'utilisateur** soit rédigé dans la langue normalisée,
tout en préservant en snake_case les clés JSON techniques et les clés de niveau de la
pyramide.

#### Scenario: Génération en français
- GIVEN une langue normalisée `"fr"`
- WHEN un prompt de génération est construit
- THEN le préambule impose un texte utilisateur en français (accents corrects, pas de snake_case pour les libellés affichés)
- AND les mots-clés de recherche d'images sont demandés en français

#### Scenario: Génération en anglais
- GIVEN une langue normalisée `"en"`
- WHEN un prompt de génération est construit
- THEN le préambule impose un texte utilisateur en anglais
- AND les mots-clés de recherche d'images sont demandés en anglais
- AND les clés JSON techniques et les clés de niveau pyramide restent en snake_case

### Requirement: Propagation de la langue aux endpoints IA
Le système SHALL accepter un champ `lang` optionnel sur les endpoints de génération IA
(proposition de discipline, création de discipline, génération de parcours et questions,
regroupement de questions, proposition Discover, ordre logique des questions, évaluation
de réponse, insights d'évaluation avancée) et l'utiliser pour la langue du contenu généré.

#### Scenario: Endpoint recevant lang=en
- GIVEN un endpoint de génération IA appelé avec `lang: "en"`
- WHEN le contenu est généré
- THEN le texte destiné à l'utilisateur est en anglais

#### Scenario: Endpoint sans lang
- GIVEN un endpoint de génération IA appelé sans champ `lang`
- WHEN le contenu est généré
- THEN le texte destiné à l'utilisateur est en français (défaut)
