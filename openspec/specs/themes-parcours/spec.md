# Themes & Parcours Specification

## Purpose
Gestion des thèmes et de leurs parcours (sous-thèmes), et génération assistée par IA des
parcours et des questions ancrés sur la pyramide des savoirs. Couvre le CRUD manuel, la
génération IA (parcours + questions) pour un thème existant ou un thème entièrement nouveau,
le regroupement des questions par familles, et la transcription audio annexe.

Routes sous `/themes` (plus un router `/subthemes`). Tables : `theme`, `subtheme` (parcours),
`question`. Modules IA : `mistral/theme_mistral.py`, `mistral/pyramid_prompts.py`.
Constantes : type de question IA par défaut `"ouverte"`, min/max parcours par appel
(`MISTRAL_MIN/MAX_DOMAINES_PER_GENERATION`, défaut 4–5), questions par parcours (défaut 10,
plage 8–12), maximum 6 familles de regroupement.

## Requirements

### Requirement: Liste des thèmes avec parcours
Le système SHALL exposer `GET /themes/all_themes`, avec filtre optionnel `id_discipline`,
renvoyant les thèmes et leurs parcours imbriqués (incluant le champ `famille` de chaque
parcours).

#### Scenario: Liste filtrée par discipline
- GIVEN des thèmes rattachés à plusieurs disciplines
- WHEN un client appelle `GET /themes/all_themes?id_discipline=N`
- THEN seuls les thèmes de la discipline N sont renvoyés, avec leurs parcours

#### Scenario: Liste complète
- WHEN un client appelle `GET /themes/all_themes` sans filtre
- THEN tous les thèmes sont renvoyés avec leurs parcours (incluant `famille`)

### Requirement: CRUD des thèmes
Le système SHALL permettre la création (`POST /themes/create_theme`), la mise à jour
(`PUT /themes/{theme_id}`) et la suppression (`DELETE /themes/{theme_id}`) de thèmes.
La création peut inclure des parcours manuels. `POST /themes/generate_theme` a un comportement
**identique** à `create_theme` (persistance manuelle, malgré son nom).

#### Scenario: Création d'un thème
- GIVEN une discipline existante
- WHEN un client envoie `POST /themes/create_theme` avec `{ label, tagline, description, id_discipline, subThemes? }`
- THEN le thème et ses éventuels parcours sont créés et renvoyés

#### Scenario: Création avec discipline inexistante
- GIVEN un `id_discipline` inexistant
- WHEN un client envoie `POST /themes/create_theme`
- THEN la réponse est `404`

#### Scenario: Mise à jour d'un thème
- GIVEN un thème existant
- WHEN un client envoie `PUT /themes/{id}` avec `{ label, tagline, description }`
- THEN la réponse est `200` avec le thème et ses parcours

#### Scenario: Suppression d'un thème
- WHEN un client envoie `DELETE /themes/{id}`
- THEN la réponse est `204` (y compris si le thème est absent — pas de contrôle 404)

### Requirement: CRUD des parcours (sous-thèmes)
Le système SHALL permettre la création d'un parcours
(`POST /themes/create_subtheme` ou `POST /themes/{theme_id}/subthemes`), sa mise à jour
(`PUT /subthemes/{subtheme_id}`) et sa suppression (`DELETE /themes/subthemes/{subtheme_id}`).

#### Scenario: Création d'un parcours
- GIVEN un thème existant
- WHEN un client envoie `POST /themes/{theme_id}/subthemes` avec `{ label, description }`
- THEN le parcours est créé et renvoyé

#### Scenario: Parcours sous thème inexistant
- GIVEN un `id_theme` inexistant
- WHEN un client crée un parcours
- THEN la réponse est `404`

#### Scenario: Mise à jour / suppression d'un parcours inexistant
- GIVEN un `subtheme_id` inexistant
- WHEN un client envoie `PUT /subthemes/{id}` ou `DELETE /themes/subthemes/{id}`
- THEN la réponse est `404`

### Requirement: Questions d'un parcours
Le système SHALL exposer `GET /themes/getQuestionsBySubTheme/{subtheme_id}` renvoyant les
questions du parcours.

#### Scenario: Liste des questions
- GIVEN un parcours avec des questions
- WHEN un client appelle `GET /themes/getQuestionsBySubTheme/{id}`
- THEN les questions du parcours sont renvoyées

### Requirement: Génération IA de parcours et questions pour un thème existant
Le système SHALL exposer `POST /themes/generate-parcours-and-questions` qui génère par IA
de nouveaux parcours (4–5 par appel, chacun avec 8–12 questions, défaut 10) pour un thème
existant, en évitant les doublons de libellés (comparaison insensible à la casse), en
persistant uniquement les nouveaux parcours, et en supportant la langue via `lang`.

#### Scenario: Génération et ajout de parcours
- GIVEN un thème existant avec du contenu
- WHEN un client envoie `POST /themes/generate-parcours-and-questions` avec `{ themeId, existing_domaines?, lang? }`
- THEN les nouveaux parcours (label non déjà présent) et leurs questions sont persistés
- AND la réponse renvoie le thème avec l'ensemble de ses parcours

#### Scenario: Tous les parcours générés sont des doublons
- GIVEN une génération dont tous les libellés existent déjà
- WHEN la persistance a lieu
- THEN aucun parcours n'est créé et le thème est renvoyé inchangé

#### Scenario: Thème inexistant ou contenu vide
- GIVEN un `themeId` inexistant
- WHEN un client appelle l'endpoint
- THEN la réponse est `404`
- AND si le thème existe mais sans contenu exploitable, la réponse est `400`

#### Scenario: Échec Mistral ou réponse partielle
- GIVEN Mistral échoue globalement
- WHEN un client appelle l'endpoint
- THEN la réponse est `502`
- AND en cas de JSON tronqué, seuls les parcours complets sont conservés (drapeau partiel)
- AND l'échec de génération des questions d'un parcours laisse ce parcours sans questions

### Requirement: Génération IA d'un thème complet
Le système SHALL exposer des variantes pour générer un thème entièrement nouveau (avec
parcours et questions) à partir d'un contexte texte : `POST /themes/generate_theme_ai/persist`
(persistance ; `{ content, id_discipline }`), les variantes par chemin
`/themes/generate_theme_ai/persist/{context}`, et un aperçu sans persistance
`GET /themes/generate_theme_ai/{context}`.

#### Scenario: Génération et persistance d'un thème
- GIVEN un contexte non vide et une discipline existante
- WHEN un client envoie `POST /themes/generate_theme_ai/persist`
- THEN un nouveau thème avec parcours et questions est persisté et renvoyé

#### Scenario: Contenu vide ou discipline manquante
- GIVEN un `content` vide
- WHEN un client appelle l'endpoint de persistance
- THEN la réponse est `400`
- AND si la discipline est absente, la réponse est `404` (ou `422` si le paramètre de discipline manque sur la variante par chemin)

#### Scenario: Aperçu sans persistance
- GIVEN un contexte
- WHEN un client appelle `GET /themes/generate_theme_ai/{context}`
- THEN la réponse contient le thème généré (`label`, `tagline`, `description`, `domaines[]` avec `questions[]`, drapeau `partial`) sans écriture en base

### Requirement: Regroupement des questions par familles
Le système SHALL exposer `POST /themes/regroupement_questions_parcours` qui regroupe par IA
les questions d'un parcours en **au plus 6 familles**, persiste `question.groupe` et
`question.libelle_groupe`, garantit que chaque question apparaît dans exactement une famille,
et bascule sur un regroupement déterministe de secours (round-robin) en cas d'échec Mistral.

#### Scenario: Regroupement réussi
- GIVEN un parcours avec des questions
- WHEN un client envoie `POST /themes/regroupement_questions_parcours` avec `{ id_subtheme, lang? }`
- THEN la réponse contient `familles[]` (≤ 6), chaque question dans une seule famille
- AND `groupe` et `libelle_groupe` sont mis à jour pour chaque question

#### Scenario: Parcours sans questions ou id invalide
- GIVEN un parcours sans question ou un `id_subtheme` invalide
- WHEN un client appelle l'endpoint
- THEN la réponse est `400`
- AND si le parcours est introuvable, la réponse est `404`

#### Scenario: Secours automatique sur échec IA
- GIVEN Mistral échoue ou renvoie un regroupement invalide
- WHEN un client appelle l'endpoint
- THEN un regroupement round-robin en ≤ 6 familles est appliqué
- AND la réponse inclut un `message` signalant le regroupement automatique

#### Scenario: Fusion des familles excédentaires
- GIVEN l'IA propose plus de 6 familles
- WHEN la réponse est normalisée
- THEN les familles en excès sont fusionnées jusqu'à en obtenir au plus 6

### Requirement: Transcription et lecture audio
Le système SHALL exposer `POST /themes/get_transcribe_audio` (upload multipart, transcription
Whisper en français, stockage `.webm`) et `GET /themes/get_audio_file/{id_audio}`
(récupération du fichier audio).

#### Scenario: Transcription audio
- GIVEN un fichier audio envoyé en multipart
- WHEN un client appelle `POST /themes/get_transcribe_audio`
- THEN la réponse contient `{ id, text }` et le fichier est stocké sous `APP_DATA_DIR/audio/`

#### Scenario: Lecture d'un audio inexistant
- GIVEN un `id_audio` inexistant
- WHEN un client appelle `GET /themes/get_audio_file/{id}`
- THEN la réponse est `404` "Audio introuvable"
