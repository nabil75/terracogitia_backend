# Disciplines Specification

## Purpose
Gestion des disciplines (matières d'apprentissage) : consultation, proposition assistée par
IA à partir d'un souhait en texte libre, création avec génération IA des thèmes, mise à jour,
suppression conditionnelle, et vue d'ensemble arborescente des connaissances.

Routes sous le préfixe `/disciplines`. Tables : `discipline` (label, description, tagline,
niveau_estime, projection), `competence`, `prerequis`, et `theme` (lié via `id_discipline`,
FK `ON DELETE SET NULL`). Modules IA : `mistral/discipline_mistral.py`.

## Requirements

### Requirement: Liste des disciplines
Le système SHALL exposer `GET /disciplines/all_disciplines` renvoyant toutes les disciplines
ordonnées par `id_discipline`.

#### Scenario: Récupération de la liste
- GIVEN des disciplines en base
- WHEN un client appelle `GET /disciplines/all_disciplines`
- THEN la réponse est `200` avec la liste ordonnée par `id_discipline`

### Requirement: Proposition de discipline assistée par IA
Le système SHALL exposer `POST /disciplines/propose_from_wish` qui, à partir d'un souhait
texte (`wish`, 3 à 4000 caractères) et d'une langue optionnelle, produit via Mistral une
proposition (label, description, compétences, prérequis, niveau estimé, projection)
**sans écriture en base**, en nettoyant/dédupliquant les champs.

#### Scenario: Proposition réussie
- GIVEN un souhait valide et Mistral disponible
- WHEN un client appelle `POST /disciplines/propose_from_wish` avec `{ wish, lang? }`
- THEN la réponse est `200` avec `label`, `description`, `competences[]`, `prerequis[]`, `niveau_estime?`, `projection?`
- AND aucune donnée n'est persistée

#### Scenario: Échec de génération
- GIVEN Mistral indisponible ou renvoyant un contenu invalide (label/description vide)
- WHEN un client appelle `POST /disciplines/propose_from_wish`
- THEN la réponse est `502`

#### Scenario: Souhait invalide
- GIVEN un `wish` de moins de 3 caractères
- WHEN un client appelle `POST /disciplines/propose_from_wish`
- THEN la réponse est `422`

### Requirement: Création d'une discipline avec thèmes générés par IA
Le système SHALL exposer `POST /disciplines/create_discipline` qui, en une transaction,
persiste la discipline, ses compétences et prérequis, puis génère par IA une liste de thèmes
squelettes (sans sous-thèmes ni questions) couvrant la pyramide dans un ordre concret →
abstrait, chaque thème portant ses métadonnées cognitives.

#### Scenario: Création réussie
- GIVEN un payload valide (`label` 1–200, listes compétences/prérequis, `lang?`)
- WHEN un client appelle `POST /disciplines/create_discipline`
- THEN la discipline, ses compétences, prérequis et les thèmes générés sont persistés atomiquement
- AND la réponse contient la discipline et ses thèmes (avec `niveau_pyramide`, `niveaux_secondaires`, `role_cognitif`, `transformation_cognitive`)

#### Scenario: Échec de génération des thèmes
- GIVEN la génération IA de la liste des thèmes échoue
- WHEN un client appelle `POST /disciplines/create_discipline`
- THEN la réponse est `502`

#### Scenario: Couverture pyramide des thèmes
- GIVEN une création de discipline
- WHEN la liste des thèmes est générée
- THEN les thèmes sont ordonnés concret → abstrait avec au moins un `faits_observables`
- AND aucun niveau dominant n'est répété plus de deux fois

### Requirement: Mise à jour d'une discipline
Le système SHALL exposer `PUT /disciplines/{disciplineId}` mettant à jour les champs
`label`, `description`, `niveau_estime`, `projection` (pas les compétences/prérequis/thèmes).

#### Scenario: Mise à jour réussie
- GIVEN une discipline existante
- WHEN un client envoie `PUT /disciplines/{id}` avec les champs modifiés
- THEN la réponse est `200` avec la discipline mise à jour

#### Scenario: Discipline inexistante
- GIVEN un id sans ligne correspondante
- WHEN un client envoie `PUT /disciplines/{id}`
- THEN la réponse est `404`

### Requirement: Suppression conditionnelle d'une discipline
Le système SHALL exposer `DELETE /disciplines/{disciplineId}` supprimant la discipline
uniquement si aucun parcours (sous-thème) n'est rattaché à ses thèmes ; sinon la suppression
est refusée. Les thèmes sans parcours ne bloquent pas la suppression (leur `id_discipline`
passe à NULL via la FK `ON DELETE SET NULL`).

#### Scenario: Suppression autorisée
- GIVEN une discipline dont les thèmes n'ont aucun parcours
- WHEN un client envoie `DELETE /disciplines/{id}`
- THEN la réponse est `204`

#### Scenario: Suppression bloquée
- GIVEN une discipline dont au moins un thème possède un parcours
- WHEN un client envoie `DELETE /disciplines/{id}`
- THEN la réponse est `409` avec un message indiquant le nombre de parcours

### Requirement: Détail d'une discipline
Le système SHALL exposer `GET /disciplines/{discipline_id}/detail` renvoyant la fiche
complète : résumé des thèmes, compétences et prérequis liés.

#### Scenario: Détail existant
- GIVEN une discipline existante
- WHEN un client appelle `GET /disciplines/{id}/detail`
- THEN la réponse est `200` avec thèmes, compétences et prérequis

#### Scenario: Détail introuvable
- GIVEN un id inexistant
- WHEN un client appelle `GET /disciplines/{id}/detail`
- THEN la réponse est `404` "Discipline introuvable"

### Requirement: Vue d'ensemble des connaissances
Le système SHALL exposer `GET /disciplines/knowledge_overview` renvoyant l'arborescence
discipline → thème → parcours → question → propositions/évaluations, en n'exposant pour les
propositions et évaluations que leur `id` et `date_creation`, en excluant les thèmes sans
discipline et les questions sans parcours.

#### Scenario: Arborescence complète
- GIVEN des disciplines avec thèmes, parcours, questions, propositions et évaluations
- WHEN un client appelle `GET /disciplines/knowledge_overview`
- THEN la réponse est une arborescence imbriquée
- AND les propositions/évaluations n'exposent que `id_*` et `date_creation` (triées par id décroissant)
- AND les thèmes sans `id_discipline` et les questions sans `id_subtheme` sont exclus
