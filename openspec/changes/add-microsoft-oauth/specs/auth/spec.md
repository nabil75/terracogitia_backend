# Auth Delta — Microsoft OAuth (OIDC)

## ADDED Requirements

### Requirement: Démarrage du flux de connexion Microsoft
Le système SHALL exposer `GET /auth/microsoft/login` qui initie un flux OpenID Connect
Authorization Code + PKCE : génération d'un `state` (anti-CSRF), d'un `nonce` (anti-rejeu) et
d'un couple PKCE, puis redirection vers l'endpoint d'autorisation de Microsoft Entra ID.

#### Scenario: Redirection vers Microsoft
- GIVEN la configuration Microsoft (tenant, client id, redirect URI) est présente
- WHEN un client appelle `GET /auth/microsoft/login`
- THEN la réponse est une redirection (302) vers l'endpoint `authorize` de Microsoft Entra ID
- AND les paramètres incluent `client_id`, `redirect_uri`, `response_type=code`, `scope` (openid profile email), `state`, `nonce` et `code_challenge` (PKCE S256)

#### Scenario: Configuration absente
- GIVEN la configuration Microsoft est incomplète
- WHEN un client appelle `GET /auth/microsoft/login`
- THEN la réponse est une erreur `500` indiquant une configuration OAuth manquante

### Requirement: Traitement du callback Microsoft
Le système SHALL exposer `GET /auth/microsoft/callback` qui vérifie le `state`, échange le
code d'autorisation contre les jetons auprès de Microsoft, et valide l'`id_token` (signature
via JWKS, `iss`, `aud`, `exp`, `nonce`) avant d'établir la connexion.

#### Scenario: Callback nominal
- GIVEN un flux initié avec un `state` valide
- WHEN Microsoft redirige vers `GET /auth/microsoft/callback?code=...&state=...`
- THEN le code est échangé contre les jetons et l'`id_token` est validé
- AND l'utilisateur est connecté puis redirigé vers l'URL frontend de retour (`APP_POST_LOGIN_REDIRECT`)

#### Scenario: State invalide (anti-CSRF)
- GIVEN un `state` absent ou ne correspondant pas au flux initié
- WHEN le callback est appelé
- THEN la connexion est refusée avec une erreur `400`
- AND aucune session n'est établie

#### Scenario: id_token invalide
- GIVEN l'`id_token` échoue à la validation (signature, `iss`, `aud`, `exp` ou `nonce`)
- WHEN le callback est traité
- THEN la connexion est refusée avec une erreur `401`
- AND aucune session n'est établie

#### Scenario: Consentement refusé
- GIVEN l'utilisateur refuse le consentement sur l'écran Microsoft
- WHEN Microsoft redirige vers le callback avec un paramètre `error`
- THEN le système redirige vers le frontend avec un état d'échec sans établir de session

### Requirement: Provisionnement et liaison de compte par email
Le système SHALL, à réception d'un `id_token` Microsoft valide, résoudre le compte par le
claim `email` : créer un nouvel utilisateur (sans mot de passe, `auth_provider = "microsoft"`)
si l'email est inconnu, ou lier le compte existant sinon, en enregistrant l'identifiant
Microsoft (`oid`) dans `azure_oid`.

#### Scenario: Email nouveau
- GIVEN aucun `users` avec l'email du jeton
- WHEN le callback réussit
- THEN un `users` est créé avec cet email, `auth_provider = "microsoft"`, `azure_oid` renseigné et sans mot de passe

#### Scenario: Email existant
- GIVEN un `users` existe déjà avec l'email du jeton
- WHEN le callback réussit
- THEN le compte existant est réutilisé et `azure_oid` y est enregistré (liaison)

#### Scenario: Email non vérifié
- GIVEN le claim email du jeton n'est pas marqué comme vérifié par Microsoft
- WHEN le callback est traité
- THEN la connexion est refusée avec une erreur `401` (aucun compte n'est créé ni lié)

### Requirement: Session serveur pour les connexions OAuth
Le système SHALL établir une session applicative après une connexion Microsoft réussie, via un
cookie `httpOnly`, `Secure`, `SameSite`, et SHALL exposer un endpoint de lecture de la session
courante et un endpoint de déconnexion. La connexion classique email/mot de passe reste
inchangée (aucune session émise) dans ce périmètre.

#### Scenario: Session établie
- GIVEN une connexion Microsoft réussie
- WHEN la réponse est renvoyée au navigateur
- THEN un cookie de session `httpOnly` est posé

#### Scenario: Lecture de la session courante
- GIVEN une session valide
- WHEN un client appelle `GET /auth/session`
- THEN la réponse `200` contient l'utilisateur courant `{ id, email, auth_provider }`

#### Scenario: Session absente ou invalide
- GIVEN aucune session valide
- WHEN un client appelle `GET /auth/session`
- THEN la réponse est `401`

#### Scenario: Déconnexion
- GIVEN une session valide
- WHEN un client appelle `POST /auth/logout`
- THEN la session est invalidée et le cookie de session est effacé
