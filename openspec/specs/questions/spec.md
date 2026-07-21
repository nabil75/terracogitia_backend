# Questions Specification

## Purpose
Opérations directes sur les questions non couvertes par la génération : gestion du dessin
(schéma Fab.js stocké en JSONB) associé à un objet identifié par `id_objet`, et import en
masse de questions depuis un fichier CSV.

Routes sous le préfixe `/questions`. Table : `question` (colonne `dessin` JSONB).
Remarque : la génération IA des questions de parcours est réalisée dans le domaine
themes-parcours (`mistral/theme_mistral.py`) ; `mistral/question_mistral.py` charge le
contexte question/parcours/proposition Discover et génère le JSON des exercices de défi
(`challenge_framework/generator.py`).
À ce stade, `id_objet` correspond à `id_question` en base ; l'identifiant est générique
côté API pour permettre une réutilisation future du dessin sur d'autres entités.

## Requirements

### Requirement: Lecture du dessin d'un objet
Le système SHALL exposer `GET /questions/{id_objet}/dessin` renvoyant le dessin
(objet JSON de canvas) associé à l'objet et un indicateur `has_dessin`.

#### Scenario: Objet avec ou sans dessin
- GIVEN un objet existant
- WHEN un client appelle `GET /questions/{id_objet}/dessin`
- THEN la réponse contient `{ id_objet, dessin, has_dessin }` (`dessin` nul si absent)

#### Scenario: Objet inexistant
- GIVEN un `id_objet` inexistant
- WHEN un client appelle `GET /questions/{id_objet}/dessin`
- THEN la réponse est `404`

### Requirement: Enregistrement du dessin d'un objet
Le système SHALL exposer `PUT /questions/{id_objet}/dessin` enregistrant un dessin, en
exigeant un objet non vide.

#### Scenario: Enregistrement réussi
- GIVEN un objet existant et un dessin non vide
- WHEN un client envoie `PUT /questions/{id_objet}/dessin` avec `{ dessin }`
- THEN la réponse indique `has_dessin: true`

#### Scenario: Dessin vide ou invalide
- GIVEN un dessin vide ou invalide
- WHEN un client envoie `PUT /questions/{id_objet}/dessin`
- THEN la réponse est `400`

### Requirement: Suppression du dessin d'un objet
Le système SHALL exposer `DELETE /questions/{id_objet}/dessin` remettant `dessin` à NULL.

#### Scenario: Suppression du dessin
- GIVEN un objet avec un dessin
- WHEN un client envoie `DELETE /questions/{id_objet}/dessin`
- THEN la réponse indique `has_dessin: false`

### Requirement: Import CSV de questions (comportement observé)
Le système SHALL exposer `PUT /questions/insert_questions/{id_subtheme}` important des
questions depuis un CSV serveur. **Comportement actuel observé** : le paramètre de chemin
`id_subtheme` est ignoré ; l'import cible un `id_subtheme` codé en dur (163) avec le type
`"ouverte"`, la première colonne du CSV servant de libellé, les lignes vides étant ignorées.

#### Scenario: Import depuis le CSV
- GIVEN un fichier CSV présent côté serveur
- WHEN un client appelle `PUT /questions/insert_questions/{id_subtheme}`
- THEN la réponse contient `{ inserted, skipped }`
- AND les questions sont insérées sous l'`id_subtheme` codé en dur (163), indépendamment du paramètre de chemin

#### Scenario: CSV manquant
- GIVEN aucun fichier CSV côté serveur
- WHEN un client appelle l'endpoint
- THEN la réponse est `404`
