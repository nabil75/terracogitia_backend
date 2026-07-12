# terra-cogitia — Backend API

API FastAPI pour la plateforme d’apprentissage **terra-cogitia** (disciplines, thèmes, parcours, questions, Discover, évaluations).

## Prérequis

- Python 3.11+
- PostgreSQL (base `terracogitia`)
- Fichier `.env` à la racine du projet

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Démarrage

```bash
uvicorn main:app --reload --port 8002
```

Documentation interactive : [http://localhost:8002/docs](http://localhost:8002/docs)

Au démarrage, le pool PostgreSQL est initialisé et les migrations idempotentes (`ALTER TABLE … IF NOT EXISTS`) sont appliquées via `database.py`.

## Variables d’environnement

### Obligatoires

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Clé API OpenAI (utilisée par certains modules) |

### Base de données

La connexion PostgreSQL est configurée dans `database.py` (`db_params`). Adapter host, user, password et nom de base selon votre environnement.

### Données applicatives (optionnel)

| Variable | Description | Défaut |
|----------|-------------|--------|
| `APP_DATA_DIR` | Répertoire des médias Discover, audio, CSV | chemin local documenté dans `config.py` |
| `MISTRAL_SECRETS_ENV` | Chemin vers un `.env` externe pour `MISTRAL_API_KEY` | chemin local documenté dans `config.py` |

### Authentification Microsoft OAuth (optionnel)

Requis uniquement pour activer **Se connecter avec Microsoft**. Sans ces variables, l’API démarre mais les endpoints `/auth/microsoft/*` renvoient une erreur 500.

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MICROSOFT_TENANT_ID` | Tenant Entra ID (`common`, tenant GUID, `organizations`, …) | `common` |
| `MICROSOFT_CLIENT_ID` | ID application Entra ID | — |
| `MICROSOFT_CLIENT_SECRET` | Secret client Entra ID | — |
| `MICROSOFT_REDIRECT_URI` | Callback backend OAuth | — |
| `APP_POST_LOGIN_REDIRECT` | URL frontend après connexion réussie | `http://localhost:4200/` |
| `APP_LOGIN_URL` | URL page login (retour en cas d’erreur OAuth) | `http://localhost:4200/login` |
| `SESSION_SECRET` | Clé de signature du cookie de session (≥ 32 caractères) | — |
| `SESSION_TTL_HOURS` | Durée de vie de la session (heures) | `8` |
| `SESSION_COOKIE_NAME` | Nom du cookie httpOnly | `tc_session` |
| `SESSION_COOKIE_SECURE` | Cookie `Secure` (`false` en dev HTTP) | `true` |

Guide détaillé Entra ID : [docs/MICROSOFT_OAUTH.md](docs/MICROSOFT_OAUTH.md)

## Endpoints d’authentification

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/auth/register` | Inscription email / mot de passe |
| `POST` | `/auth/login` | Connexion classique (sans session cookie) |
| `POST` | `/auth/reset_password` | Réinitialisation mot de passe |
| `GET` | `/auth/microsoft/login` | Démarre le flux OAuth Microsoft |
| `GET` | `/auth/microsoft/callback` | Callback OAuth (usage interne Microsoft) |
| `GET` | `/auth/session` | Utilisateur courant (cookie de session) |
| `POST` | `/auth/logout` | Déconnexion (efface le cookie) |

## Tests

```bash
pip install -r requirements.txt
pytest
```

Les tests OAuth mockent Microsoft Entra ID et PostgreSQL ; aucune connexion externe n’est requise.

## OpenSpec

Spécifications et changements : dossier `openspec/`.

- Specs de référence : `openspec/specs/`
- Change Microsoft OAuth : `openspec/changes/add-microsoft-oauth/`

## Structure du projet

```
main.py              # Point d’entrée FastAPI, CORS, routers
config.py            # Variables d’environnement
database.py          # Pool asyncpg + migrations idempotentes
routers/             # Endpoints par domaine
mistral/             # Prompts et clients IA
session_utils.py     # Session cookie JWT (OAuth Microsoft)
docs/                # Documentation complémentaire
tests/               # Tests pytest
```
