# Pyramid Knowledge Model Specification

## Purpose
Modèle pédagogique central « pyramide des savoirs » qui structure tout le contenu généré :
6 niveaux ordonnés du concret vers l'abstrait, un ensemble de transformations cognitives,
une grille de familles par niveau, et des opérations cognitives associées aux questions.
Ce modèle contraint la génération IA des thèmes, parcours et questions et sert de base aux
analyses d'évaluation avancée.

Fichier central : `mistral/pyramid_prompts.py`.

## Requirements

### Requirement: Six niveaux canoniques de la pyramide
Le système SHALL reconnaître exactement six niveaux de pyramide, identifiés par des clés
snake_case, dans l'ordre concret → abstrait : `faits_observables`, `lois_relations`,
`schemes_operatoires`, `principes_generateurs`, `structures_abstraites`,
`metacadres_theoriques`.

#### Scenario: Normalisation d'un niveau
- GIVEN une valeur de niveau saisie avec accents, espaces ou variantes françaises
- WHEN `normalize_pyramid_level` est appliquée
- THEN elle renvoie la clé canonique correspondante, ou `None` si aucune correspondance

#### Scenario: Liste de niveaux dédupliquée
- GIVEN une liste de niveaux contenant des doublons ou des valeurs invalides
- WHEN `normalize_pyramid_level_list` est appliquée
- THEN elle renvoie une liste de clés canoniques uniques

### Requirement: Transformations cognitives
Le système SHALL reconnaître un ensemble fixe de transformations cognitives
(`observer`, `comparer`, `relier`, `resoudre`, `generaliser`, `modeliser`, `critiquer`,
`integrer`) et SHALL normaliser toute valeur reçue vers l'une d'elles ou `None`.

#### Scenario: Normalisation d'une transformation
- GIVEN une transformation cognitive saisie librement
- WHEN `normalize_transformation_cognitive` est appliquée
- THEN elle renvoie la transformation canonique ou `None`

### Requirement: Opérations cognitives des questions et familles
Le système SHALL associer à chaque question une opération cognitive (verbe, ex. `observer`,
`expliquer`, `appliquer`) rattachée à une famille d'opérations
(observation, comprehension, application, generalisation, modelisation, reflexion), distincte
de la notion de niveau de pyramide.

#### Scenario: Famille d'une opération
- GIVEN une opération cognitive canonique
- WHEN sa famille est demandée via `cognitive_operation_family`
- THEN elle renvoie la famille correspondante, ou `other` si inconnue

### Requirement: Grille des familles par niveau
Le système SHALL fournir, pour la génération de parcours, une grille énumérant des familles
candidates par niveau de pyramide, avec la règle : chaque famille pertinente peut donner lieu
à **un** parcours distinct, aucune famille ne doit être inventée hors grille, et le
`role_cognitif` du parcours doit nommer la famille visée.

#### Scenario: Sélection de parcours par famille
- GIVEN un niveau de pyramide visé pour un thème
- WHEN la génération de parcours parcourt la grille des familles de ce niveau
- THEN seules les familles réellement pertinentes produisent un parcours
- AND le `role_cognitif` de chaque parcours nomme sa famille

### Requirement: Profil de questions par défaut
Le système SHALL calculer un profil de répartition de questions pour un niveau dominant et
un total donné (défaut 10), en plaçant environ 40 % des questions au niveau dominant et en
répartissant le reste vers les niveaux supérieurs, avec au moins une question au niveau
dominant.

#### Scenario: Répartition par défaut
- GIVEN un niveau dominant et un total T (défaut 10)
- WHEN `_default_profil_questions` est calculé
- THEN au moins ~40 % des questions sont au niveau dominant
- AND le reste est réparti vers les niveaux supérieurs de la pyramide

### Requirement: Couverture pyramide guidée par prompt
Le système SHALL assurer la couverture des niveaux de la pyramide par instruction du prompt
(ordre concret → abstrait, ancrage sur un niveau dominant, contrôle de couverture), sans
validation programmatique post-génération.

#### Scenario: Contrôle de couverture demandé
- GIVEN une génération de parcours
- WHEN le prompt est construit
- THEN il demande un objet `controle_pyramide` avec `niveaux_couverts`, `familles_couvertes` et `ordre_respecte`
- AND la conformité repose sur le respect des consignes par le LLM (pas de rejet automatique côté serveur)
