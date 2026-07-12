# Discover Specification

## Purpose
Fonctionnalité « Discover » : génération par IA d'une proposition pédagogique structurée pour
une question (introduction, contexte, analyse, conclusion, exercice) enrichie d'images issues
de Pexels ; gestion des propositions sauvegardées (une seule « courante » par question), des
notes, et de l'ordre logique (graphe de prérequis) des questions d'un parcours avec mise en
cache.

Routes sous le préfixe `/discovering`. Modules : `mistral/discovering_mistral.py`,
`discover_pexels.py`, `discover_media_storage.py`. Tables : `proposition`
(`statut_current`, `notes`, `date_creation`), `subtheme.timeline` (cache JSONB).

## Requirements

### Requirement: Génération d'une proposition Discover
Le système SHALL exposer
`GET /discovering/get_proposition_for_question/{question}/{subtheme}` qui génère via Mistral
une proposition structurée dans la langue demandée (`?lang=fr|en`), enrichie d'images Pexels,
en exigeant que les sections `Analyse` et `exercice` soient non vides.

#### Scenario: Génération réussie
- GIVEN `MISTRAL_API_KEY` valide (et éventuellement `PEXELS_API_KEY`)
- WHEN un client appelle `GET /discovering/get_proposition_for_question/{q}/{sub}?lang=fr`
- THEN la réponse contient les sections structurées, `Analyse` et `exercice` non vides
- AND des mots-clés et liens d'images (jusqu'à 5 par section) sont fournis si Pexels est configuré

#### Scenario: Réponse IA incomplète
- GIVEN Mistral renvoie une `Analyse` ou un `exercice` vide, ou un JSON invalide/tronqué
- WHEN un client appelle l'endpoint
- THEN la réponse est `502`

#### Scenario: Pexels non configuré vs clé invalide
- GIVEN `PEXELS_API_KEY` absente
- WHEN une proposition est générée
- THEN les tableaux d'images sont vides sans erreur
- AND si la clé Pexels est présente mais invalide, la réponse est `500`

### Requirement: Stockage des images de proposition
Le système SHALL télécharger et stocker les images issues de Pexels soit sur S3 (si toutes les
variables AWS sont configurées), soit localement sous `APP_DATA_DIR/discover_media`, et exposer
une URL publique (préfixe `DISCOVER_MEDIA_PUBLIC_BASE_URL`/`CDN_BASE_URL` ou URL S3).

#### Scenario: Priorité S3 puis local
- GIVEN un bucket S3 et des identifiants AWS complets
- WHEN une image est stockée
- THEN elle est envoyée sur S3 et l'URL S3 est renvoyée
- AND sinon elle est stockée localement et servie via `/media/discover/`

### Requirement: Liste des propositions sauvegardées d'une question
Le système SHALL exposer
`GET /discovering/get_saved_propositions_by_question/{id_question}` renvoyant toutes les
propositions sauvegardées, après normalisation garantissant qu'au plus une proposition est
`statut_current = true` par question.

#### Scenario: Récupération avec normalisation
- GIVEN plusieurs propositions pour une question
- WHEN un client appelle l'endpoint
- THEN la liste est renvoyée avec exactement une proposition marquée courante (si au moins une existe)
- AND `date_creation` est au format `DD/MM/YYYY HH:MM`

### Requirement: Sauvegarde d'une proposition
Le système SHALL exposer `POST /discovering/store_saved_proposition` (201) acceptant un
identifiant de question sous plusieurs noms de champ tolérés et un contenu de proposition,
insérant la nouvelle proposition comme courante et rétrogradant les autres.

#### Scenario: Sauvegarde réussie
- GIVEN un identifiant de question et un contenu de proposition
- WHEN un client envoie `POST /discovering/store_saved_proposition`
- THEN la réponse est `201`, la nouvelle proposition est `statut_current = true`
- AND toutes les autres propositions de la question passent à `statut_current = false`

#### Scenario: Identifiant ou contenu manquant
- GIVEN un payload sans identifiant de question ou sans contenu de proposition
- WHEN un client appelle l'endpoint
- THEN la réponse est `422`

### Requirement: Suppression d'une proposition
Le système SHALL exposer `DELETE /discovering/delete_saved_proposition/{id_proposition}`
(204) supprimant une proposition et, si elle était courante, promouvant la plus récente
restante comme courante.

#### Scenario: Suppression de la proposition courante
- GIVEN une proposition courante et d'autres propositions pour la même question
- WHEN un client la supprime
- THEN la réponse est `204` et la plus récente restante devient courante

#### Scenario: Proposition inexistante
- GIVEN un `id_proposition` inexistant
- WHEN un client appelle l'endpoint
- THEN la réponse est `404`

### Requirement: Changement de proposition courante
Le système SHALL exposer `PATCH /discovering/set_current_proposition/{id_proposition}`
définissant la proposition cible comme courante et rétrogradant ses sœurs.

#### Scenario: Bascule de la proposition courante
- GIVEN plusieurs propositions pour une question
- WHEN un client envoie `PATCH /discovering/set_current_proposition/{id}`
- THEN la cible devient `statut_current = true` et les autres `false`

#### Scenario: Cible inexistante
- GIVEN un `id_proposition` inexistant
- WHEN un client appelle l'endpoint
- THEN la réponse est `404`

### Requirement: Notes sur la proposition courante
Le système SHALL exposer `PUT /discovering/question_proposition_notes/{id_question}` mettant à
jour les notes de la proposition courante ; si aucune proposition n'existe et que les notes ne
sont pas vides, une proposition vide courante est créée pour les porter.

#### Scenario: Mise à jour des notes
- GIVEN une question avec une proposition courante
- WHEN un client envoie `PUT /discovering/question_proposition_notes/{id}` avec `{ notes }`
- THEN les notes de la proposition courante sont mises à jour

#### Scenario: Notes de type invalide
- GIVEN un champ `notes` qui n'est pas une chaîne
- WHEN un client appelle l'endpoint
- THEN la réponse est `422`

### Requirement: Ordre logique des questions (graphe de prérequis)
Le système SHALL exposer `POST /discovering/ordre_logique_questions` qui calcule ou récupère
en cache le graphe de prérequis entre les questions d'un parcours, avec un mode `legacy`
(objet brut par libellés, non persisté sur cache-miss) et un mode enrichi
(`legacy=false` : vues UI, tri topologique, persistance dans `subtheme.timeline`), et un
`force_refresh` pour ignorer le cache.

#### Scenario: Génération enrichie et persistance
- GIVEN un parcours et sa liste de questions
- WHEN un client envoie `POST /discovering/ordre_logique_questions?legacy=false`
- THEN le graphe est généré, transformé en vues UI, trié topologiquement et persisté dans `subtheme.timeline`

#### Scenario: Cache valide
- GIVEN un cache dont la signature `question_ids` correspond à l'ensemble courant
- WHEN un client appelle l'endpoint sans `force_refresh`
- THEN le résultat est renvoyé depuis le cache sans appel Mistral

#### Scenario: Cycle détecté
- GIVEN un graphe de prérequis contenant un cycle
- WHEN le tri topologique est effectué
- THEN la réponse est marquée `partial: true`

#### Scenario: Liste vide ou parcours invalide
- GIVEN une liste de questions vide
- WHEN un client appelle l'endpoint
- THEN la réponse est `{}`
- AND si `id_subtheme` n'est pas un entier ≥ 1, la réponse est `400`

#### Scenario: Échec Mistral
- GIVEN Mistral échoue ou renvoie un JSON invalide
- WHEN un client appelle l'endpoint (hors cache)
- THEN la réponse est `502`

### Requirement: Lecture de la timeline en cache
Le système SHALL exposer `GET /discovering/subtheme_timeline/{subtheme_id}` renvoyant la
timeline persistée (sans appel LLM), avec un indicateur `from_cache`.

#### Scenario: Timeline présente
- GIVEN une timeline persistée pour le parcours
- WHEN un client appelle `GET /discovering/subtheme_timeline/{id}`
- THEN le document enrichi est renvoyé avec `from_cache: true`

#### Scenario: Timeline absente
- GIVEN aucune timeline persistée
- WHEN un client appelle l'endpoint
- THEN la réponse contient `{ id_subtheme, from_cache: false }`
