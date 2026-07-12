# Design: Authentification Microsoft (OAuth 2.0 / OIDC) — Backend

## Contexte
L'application est aujourd'hui **stateless** : `POST /auth/login` vérifie les identifiants et
renvoie `{ ok, id, email }` sans émettre de session ni de jeton. Toutes les routes sont
publiques. Ajouter OAuth impose donc de trancher la question de la session serveur.

## Approche technique
Flux **Authorization Code + PKCE** orchestré côté serveur (Backend-for-Frontend) contre
Microsoft Entra ID (OpenID Connect).

```
Frontend            Backend                         Microsoft Entra ID
   │  GET /auth/microsoft/login                          │
   │ ───────────────▶ │  génère state+nonce+PKCE          │
   │                  │  redirige vers /authorize ───────▶│
   │ ◀──────────────────────── écran de consentement ────│
   │                  │  callback ?code&state             │
   │                  │ ◀───────────────────────────────  │
   │                  │  échange code → tokens (/token) ─▶ │
   │                  │  valide id_token (JWKS)            │
   │                  │  provisionne/lie users             │
   │                  │  pose cookie de session httpOnly   │
   │ ◀── redirect app │                                    │
```

## Décisions d'architecture

### Decision: Flux serveur (BFF) plutôt que SPA + MSAL.js
Retenu : échange du code et validation des jetons côté serveur.
- Le client secret et les jetons Microsoft ne transitent jamais par le navigateur.
- Cohérent avec un backend FastAPI déjà présent.
- Alternative écartée : SPA avec `@azure/msal-browser` (PKCE public client). Plus simple à câbler
  côté front mais expose la gestion de jetons au navigateur et complique la validation côté API.

### Decision: Session serveur via cookie httpOnly (jeton signé sans état)
Retenu : émettre, après succès OIDC, un cookie de session `httpOnly`, `Secure`, `SameSite=Lax`
contenant un **jeton signé (HMAC/JWT) sans magasin serveur**, avec expiration (défaut : 8 h) et
signature par `SESSION_SECRET`.
- Introduit la première vraie session de l'application.
- Pas de table `session` au départ : simplicité et zéro état côté serveur.
- La déconnexion efface le cookie (invalidation côté client). La révocation serveur (liste de
  jetons invalidés / table `session`) est un ajout ultérieur si le besoin apparaît.

### Decision: Audience de comptes = `common` (personnels + pro/scolaires), configurable
Retenu : `MICROSOFT_TENANT_ID` par défaut `common`, acceptant les comptes Microsoft personnels
et professionnels/scolaires, pour maximiser l'accès sur une plateforme éducative.
- Configurable : peut être restreint à un tenant précis ou à `organizations` selon le
  déploiement, sans changement de code.
- `iss` et `aud` sont validés dans tous les cas.

### Decision: Provisionnement / liaison de compte par email
Retenu : à la réception d'un `id_token` valide, résoudre le compte par `email` (claim vérifié) :
- email inconnu → créer un `users` sans mot de passe, marqué provider `microsoft`.
- email connu → lier le compte existant en enregistrant l'`oid` Microsoft.
- Enregistrer `azure_oid` (identifiant stable Microsoft) et `auth_provider`.

### Decision: Coexistence avec la connexion classique
Les deux mécanismes coexistent. La connexion email/mot de passe conserve son comportement
actuel (renvoie `{ ok, id, email }`, sans session) pour ce changement. L'unification (émettre
aussi une session pour la connexion classique, ajouter la protection de routes) est **différée**.

## Changements de données
Table `users` : ajouter (idempotent, `ADD COLUMN IF NOT EXISTS`) :
- `azure_oid TEXT` (unique lorsque non nul) — identifiant Microsoft `oid`.
- `auth_provider TEXT DEFAULT 'local'` — `'local'` | `'microsoft'`.
- `hashed_password` devient nullable pour les comptes Microsoft.
- `display_name TEXT` (optionnel).

## Sécurité
- Vérifier `state` (anti-CSRF) et `nonce` (anti-rejeu) stockés le temps du flux.
- Valider l'`id_token` : signature via JWKS Entra ID, `iss`, `aud` (= client id), `exp`, `nonce`.
- PKCE `S256`.
- Cookie de session `httpOnly` + `Secure` + `SameSite`.
- Ne jamais journaliser les jetons ni le code.
- CORS : les origines dev restent `http://localhost:4200` / `127.0.0.1:4200` ; ajouter les
  origines de production lors du déploiement.

## Configuration (variables d'environnement)
- `MICROSOFT_TENANT_ID` (défaut `common` ; ou un tenant précis / `organizations` / `consumers`).
- `MICROSOFT_CLIENT_ID`.
- `MICROSOFT_CLIENT_SECRET`.
- `MICROSOFT_REDIRECT_URI` (callback backend, ex. `http://localhost:8002/auth/microsoft/callback`).
- `APP_POST_LOGIN_REDIRECT` (URL frontend de retour, ex. `http://localhost:4200/`).
- `SESSION_SECRET` (signature du cookie de session).
- `SESSION_TTL_HOURS` (durée de vie de la session, défaut 8).

## Décisions finalisées (recommandations par défaut retenues)
Ces points, précédemment ouverts, sont désormais tranchés pour ce changement :

1. **Audience de comptes** → `common` (comptes personnels + professionnels/scolaires),
   configurable via `MICROSOFT_TENANT_ID`. Cf. « Decision: Audience de comptes ».
2. **Session** → jeton signé **sans état** (HMAC/JWT), cookie httpOnly, TTL 8 h ; pas de table
   `session` au départ ; révocation serveur différée. Cf. « Decision: Session serveur ».
3. **Unification de la connexion classique** → **différée**. La connexion email/mot de passe
   reste inchangée (renvoie `{ ok, id, email }`, sans session) dans ce périmètre. Une évolution
   ultérieure pourra lui faire émettre la même session.
4. **Protection des routes** → **différée**. Aucune dépendance d'auth n'est ajoutée sur les
   routes existantes dans ce changement ; `GET /auth/session` permet au frontend de connaître
   l'état connecté. Le durcissement des routes sensibles (ex. admin) fera l'objet d'un
   changement dédié.
5. **Email non vérifié** → **connexion refusée** (`401`) si le claim email n'est pas marqué
   vérifié par Microsoft. Aucun compte n'est créé ni lié. Cf. delta `auth` (scénario « Email
   non vérifié »).

Note : ces décisions étant figées, tout écart devra passer par une révision explicite de ce
`design.md`.
