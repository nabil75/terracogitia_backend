# Platform Specification

## Purpose
Comportements transverses de la plateforme backend : démarrage de l'application,
initialisation de la base de données et migrations idempotentes, configuration par
variables d'environnement, politique CORS, et service statique des médias Discover.

Fichiers concernés : `main.py`, `config.py`, `database.py`, `queries.py`.

## Requirements

### Requirement: Cycle de vie de l'application
Le système SHALL initialiser un pool de connexions PostgreSQL au démarrage (avant tout
traitement de requête) et SHALL le fermer à l'arrêt, via le hook `lifespan` de FastAPI.

#### Scenario: Démarrage nominal
- GIVEN une base PostgreSQL `terracogitia` joignable
- WHEN l'application démarre
- THEN `init_db()` crée le pool asyncpg et exécute les migrations idempotentes
- AND le répertoire `APP_DATA_DIR/discover_media` est créé
- AND les routers `theme`, `subthemes`, `discipline`, `discovering`, `question`, `auth`, `microsoft_oauth`, `challenges` sont enregistrés

#### Scenario: Requête avant initialisation du pool
- GIVEN le pool de connexions n'est pas initialisé
- WHEN un endpoint qui interroge la base est appelé
- THEN la réponse est `500` (pool indisponible)

#### Scenario: Arrêt de l'application
- WHEN l'application s'arrête
- THEN `close_db()` ferme proprement le pool de connexions

### Requirement: Politique CORS
Le système SHALL autoriser les requêtes cross-origin uniquement depuis le frontend de
développement (`http://localhost:4200` et `http://127.0.0.1:4200`), avec credentials,
toutes méthodes et tous en-têtes.

#### Scenario: Origine autorisée
- GIVEN une requête provenant de `http://localhost:4200`
- WHEN elle atteint l'API
- THEN les en-têtes CORS autorisent la réponse avec credentials

#### Scenario: Origine non autorisée
- GIVEN une requête provenant d'une origine non listée
- WHEN le navigateur applique la politique CORS
- THEN la requête cross-origin est refusée côté navigateur

### Requirement: Service statique des médias Discover
Le système SHALL servir les fichiers image stockés localement pour Discover via
`GET /media/discover/{filename}` depuis `APP_DATA_DIR/discover_media`.

#### Scenario: Média existant
- GIVEN un fichier image stocké dans `APP_DATA_DIR/discover_media`
- WHEN un client demande `GET /media/discover/{filename}`
- THEN le fichier est renvoyé

### Requirement: Migrations de schéma idempotentes au démarrage
Le système SHALL appliquer au démarrage, de façon idempotente, les évolutions de schéma
nécessaires (ajouts de colonnes `IF NOT EXISTS`, créations de tables `IF NOT EXISTS`,
index) afin que la base existante soit mise à niveau sans intervention manuelle.

#### Scenario: Colonnes pyramide ajoutées si absentes
- GIVEN une base sans les colonnes enrichies
- WHEN `init_db()` s'exécute
- THEN les colonnes pyramide sur `subtheme` (niveau_pyramide, role_cognitif, transformations_cognitives, prerequis, ouvre_vers, niveaux_secondaires, profil_questions_attendu, famille, timeline) et sur `question` (niveau_pyramide, operation_cognitive, objectif_pedagogique, concepts_vises, prerequis_concepts, groupe, libelle_groupe, dessin) existent
- AND les tables legacy d'évaluation (`evaluation`, `reponse_evaluation`, `subtheme_session`, `discover_activity`) sont supprimées si présentes
- AND les tables `competence`, `prerequis` existent

#### Scenario: Consolidation de la colonne legacy niveau_cognitif
- GIVEN une base contenant l'ancienne colonne `question.niveau_cognitif`
- WHEN `init_db()` s'exécute
- THEN les valeurs sont recopiées dans `operation_cognitive` lorsque celle-ci est nulle
- AND la colonne `niveau_cognitif` est supprimée
- AND l'opération ne s'exécute pas si la colonne a déjà été supprimée (idempotence)

### Requirement: Configuration par variables d'environnement
Le système SHALL charger sa configuration depuis un `.env` projet puis un fichier de
secrets externe (`MISTRAL_SECRETS_ENV`) qui **écrase** les clés déjà chargées, et SHALL
échouer au démarrage si une clé strictement requise est absente.

#### Scenario: Secrets externes prioritaires
- GIVEN un `MISTRAL_API_KEY` défini à la fois dans le `.env` projet et dans le fichier de secrets externe
- WHEN la configuration est chargée
- THEN la valeur du fichier de secrets externe prévaut

#### Scenario: Clé requise manquante
- GIVEN `OPENAI_API_KEY` absent de l'environnement
- WHEN le module de configuration est importé
- THEN l'application échoue à l'import avec une `ValueError`

#### Scenario: Racine de données configurable
- GIVEN `APP_DATA_DIR` défini
- WHEN l'application accède aux médias, audios ou CSV
- THEN les chemins sont résolus sous `APP_DATA_DIR`
