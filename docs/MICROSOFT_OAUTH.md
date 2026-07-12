# Authentification Microsoft (Entra ID)

Ce guide décrit la configuration de l’application **Microsoft Entra ID** (Azure AD) pour le flux OAuth 2.0 / OpenID Connect utilisé par terra-cogitia.

## Prérequis

- Un compte [Microsoft Entra admin center](https://entra.microsoft.com/) (Azure Portal → Microsoft Entra ID).
- Backend terra-cogitia accessible depuis Internet **ou** en local pour les tests (`http://localhost:8002`).
- Frontend Angular (`http://localhost:4200` en développement).

## 1. Enregistrer l’application

1. Ouvrir **Microsoft Entra ID** → **Applications** → **Inscriptions d’applications** → **Nouvelle inscription**.
2. **Nom** : `terra-cogitia` (ou nom de votre choix).
3. **Types de comptes pris en charge** :
   - Développement / accès large : **Comptes dans un annuaire d’organisation et comptes Microsoft personnels**.
   - Production scolaire restreinte : choisir **Mon organisation uniquement** et renseigner `MICROSOFT_TENANT_ID` avec l’ID de votre tenant.
4. **URI de redirection** (type **Web**) :
   ```
   http://localhost:8002/auth/microsoft/callback
   ```
   En production, ajouter l’URL correspondante, par ex. :
   ```
   https://api.votre-domaine.fr/auth/microsoft/callback
   ```
5. Valider **Inscrire**.

## 2. Récupérer les identifiants

Sur la page **Vue d’ensemble** de l’application :

| Valeur Entra ID | Variable d’environnement backend |
|-----------------|----------------------------------|
| ID d’application (client) | `MICROSOFT_CLIENT_ID` |
| ID de l’annuaire (locataire) | `MICROSOFT_TENANT_ID` (optionnel, défaut `common`) |

Sous **Certificats et secrets** → **Nouveau secret client** :

| Valeur | Variable |
|--------|----------|
| Valeur du secret (copiée immédiatement) | `MICROSOFT_CLIENT_SECRET` |

## 3. Permissions API

Sous **Autorisations API** → **Ajouter une autorisation** → **Microsoft Graph** → **Autorisations déléguées** :

- `openid` (inclus dans OpenID Connect)
- `profile`
- `email`

Aucune permission **Application** n’est requise pour ce flux (Authorization Code + PKCE côté serveur).

Accorder le **consentement administrateur** si votre tenant l’exige.

## 4. Variables d’environnement backend

Ajouter dans le fichier `.env` du backend (ou variables d’environnement du déploiement) :

```env
# Microsoft Entra ID
MICROSOFT_TENANT_ID=common
MICROSOFT_CLIENT_ID=<votre-client-id>
MICROSOFT_CLIENT_SECRET=<votre-client-secret>
MICROSOFT_REDIRECT_URI=http://localhost:8002/auth/microsoft/callback

# Redirections frontend
APP_POST_LOGIN_REDIRECT=http://localhost:4200/
APP_LOGIN_URL=http://localhost:4200/login

# Session (cookie httpOnly signé)
SESSION_SECRET=<chaîne aléatoire longue, ≥ 32 caractères>
SESSION_TTL_HOURS=8
SESSION_COOKIE_NAME=tc_session
SESSION_COOKIE_SECURE=false
```

Notes :

- `MICROSOFT_TENANT_ID=common` accepte comptes personnels et professionnels/scolaires.
- `SESSION_COOKIE_SECURE=false` uniquement en dev HTTP ; mettre `true` (défaut) en HTTPS production.
- `MICROSOFT_REDIRECT_URI` doit correspondre **exactement** à l’URI enregistrée dans Entra ID.

## 5. CORS et cookies

Le backend autorise déjà `http://localhost:4200` avec `allow_credentials=True`. En production, ajouter l’origine du frontend dans `main.py` (`origins`).

Le frontend appelle `GET /auth/session` et `POST /auth/logout` avec `withCredentials: true` pour transmettre le cookie de session.

## 6. Flux utilisateur

1. L’utilisateur clique **Se connecter avec Microsoft** sur `/login`.
2. Le navigateur appelle `GET /auth/microsoft/login` (backend).
3. Redirection vers Microsoft → authentification / consentement.
4. Microsoft rappelle `GET /auth/microsoft/callback?code=…&state=…`.
5. Le backend valide `state`, échange le code, vérifie l’`id_token`, crée ou lie le compte, pose le cookie de session.
6. Redirection vers `APP_POST_LOGIN_REDIRECT` (page d’accueil).

En cas d’échec (consentement refusé, etc.), redirection vers `APP_LOGIN_URL?auth_error=<code>`.

## 7. Vérification

1. Démarrer le backend : `uvicorn main:app --reload --port 8002`
2. Démarrer le frontend : `ng serve`
3. Ouvrir `http://localhost:4200/login` → **Se connecter avec Microsoft**
4. Après connexion, vérifier :
   ```bash
   curl -b cookies.txt http://localhost:8002/auth/session
   ```
   (ou via les outils réseau du navigateur avec le cookie `tc_session`)

## 8. Dépannage

| Symptôme | Cause probable |
|----------|----------------|
| `redirect_uri_mismatch` | URI callback différente entre Entra ID et `MICROSOFT_REDIRECT_URI` |
| `Configuration OAuth Microsoft manquante` | Variables `MICROSOFT_*` ou `SESSION_SECRET` absentes |
| Cookie de session absent | `SESSION_COOKIE_SECURE=true` sur HTTP non localhost |
| `401` après callback | Secret client expiré, `aud`/`iss` invalides, ou email non vérifié (`email_verified=false`) |
| CORS bloqué | Origine frontend non listée dans `origins` ou requête sans `withCredentials` |

## Références

- [Microsoft identity platform — Authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [OpenID Connect on Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc)
- Change OpenSpec : `openspec/changes/add-microsoft-oauth/design.md`
