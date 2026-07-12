# Tasks — Backend

## 1. Configuration & données
- [x] 1.1 Ajouter les variables d'environnement Microsoft (`MICROSOFT_TENANT_ID` défaut `common`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_REDIRECT_URI`, `APP_POST_LOGIN_REDIRECT`, `SESSION_SECRET`, `SESSION_TTL_HOURS` défaut 8) dans `config.py`
- [x] 1.2 Migration idempotente `users` : `azure_oid`, `auth_provider`, `display_name`, rendre `hashed_password` nullable (dans `database.py` + fichier `.sql`)
- [x] 1.3 Index unique conditionnel sur `azure_oid` (non nul)

## 2. Flux OIDC
- [x] 2.1 `GET /auth/microsoft/login` : générer `state`, `nonce`, PKCE ; stocker temporairement ; rediriger vers l'endpoint `authorize` Entra ID
- [x] 2.2 `GET /auth/microsoft/callback` : vérifier `state`, échanger le `code` contre les jetons (`token`)
- [x] 2.3 Récupérer et mettre en cache les clés JWKS ; valider l'`id_token` (signature, `iss`, `aud`, `exp`, `nonce`)
- [x] 2.4 Gérer les erreurs du fournisseur (consentement refusé, code invalide, jeton invalide)

## 3. Comptes & session
- [x] 3.1 Provisionner/lier le compte par email (créer si nouveau, lier `azure_oid` sinon)
- [x] 3.2 Émettre une session sous forme de jeton signé sans état (HMAC/JWT, TTL `SESSION_TTL_HOURS`) dans un cookie httpOnly, Secure, SameSite après succès
- [x] 3.3 `POST /auth/logout` : invalider la session / effacer le cookie
- [x] 3.4 `GET /auth/session` (ou `/auth/me`) : renvoyer l'utilisateur courant si session valide

## 4. Sécurité & tests
- [x] 4.1 Vérifier anti-CSRF (`state`) et anti-rejeu (`nonce`)
- [x] 4.2 Ne pas journaliser code/jetons
- [x] 4.3 Tests : callback nominal, `state` invalide, `id_token` invalide, email connu vs nouveau, déconnexion

## 5. Documentation
- [x] 5.1 Documenter la configuration de l'app Entra ID (redirect URI, permissions `openid profile email`)
- [x] 5.2 Mettre à jour le README backend (variables d'environnement)
