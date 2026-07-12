# Challenge Evaluation Specification

## Purpose
Domaine **à venir** : évaluation des connaissances acquises et maîtrisées par l'apprenant via
des **défis sous forme de jeux**, et non plus via la notation IA des réponses aux questions.

L'ancien dispositif (évaluation simple `/evaluations` et évaluation avancée
`/advanced-evaluation`, tables `evaluation`, `reponse_evaluation`, `subtheme_session`,
`discover_activity`) a été **supprimé** pour faire place nette.

## État actuel

- Aucun endpoint d'évaluation n'est exposé.
- Aucune table d'évaluation n'est créée au démarrage (`database.py` supprime les tables legacy).
- Le contenu pédagogique (disciplines, thèmes, parcours, questions) et Discover restent en place.

## Requirements (futurs — non implémentés)

### Requirement: Défis ludiques par parcours
Le système SHALL, dans une version ultérieure, proposer des défis (jeux) associés aux
parcours, avec des règles de création et de scoring définies dans une spec dédiée.

#### Scenario: Placeholder
- GIVEN le dispositif legacy supprimé
- WHEN une spec de défis sera rédigée
- THEN elle remplacera ce document par des exigences concrètes (API, persistance, UI)
