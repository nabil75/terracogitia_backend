# Proposal: Authentification Microsoft (OAuth 2.0 / OIDC)

## Intent
Permettre aux utilisateurs de se connecter à Terra Cogitia avec leur compte Microsoft
(Microsoft Entra ID / Azure AD, comptes personnels et/ou professionnels) en plus de la
connexion email + mot de passe existante. Objectifs : réduire la friction d'inscription,
supprimer la gestion de mot de passe pour ces utilisateurs, et s'appuyer sur un fournisseur
d'identité éprouvé.

Ce changement concerne le **backend** (flux OIDC, provisionnement de compte, session serveur).
Le bouton « Se connecter avec Microsoft » et la gestion du retour de redirection côté client
font l'objet d'un changement coordonné de même nom dans le dépôt frontend.

## Scope
Dans le périmètre :
- Endpoints backend pour démarrer le flux OIDC et traiter le callback Microsoft.
- Flux Authorization Code + PKCE contre Microsoft Entra ID (endpoints `authorize` / `token`),
  validation de l'`id_token` (signature, `iss`, `aud`, `exp`, `nonce`).
- Provisionnement / liaison de compte par email : création d'un `users` si l'email est
  nouveau, liaison au compte existant sinon, en enregistrant l'identifiant Microsoft (`oid`).
- Session serveur pour les connexions OAuth via cookie httpOnly (première introduction d'une
  vraie session dans l'application, aujourd'hui stateless), avec un endpoint de déconnexion.
- Configuration par variables d'environnement (tenant, client id/secret, redirect URI).

Hors périmètre :
- Autres fournisseurs (Google, GitHub…).
- Rôles / autorisations / RBAC.
- Migration de la connexion email/mot de passe existante vers le nouveau mécanisme de session
  (les deux coexistent ; l'unification est une décision différée — cf. design).
- Synchronisation de profil au-delà de l'email et du nom d'affichage.

## Approach
Utiliser le flux **Authorization Code avec PKCE** orchestré côté serveur (pattern
Backend-for-Frontend) : le backend construit l'URL d'autorisation Microsoft, reçoit le code sur
un callback, l'échange contre les jetons, valide l'`id_token`, provisionne/lie le compte par
email, puis établit une session applicative via un cookie httpOnly. Le frontend n'expose ni le
client secret ni les jetons Microsoft.

Voir `design.md` pour les décisions détaillées, les alternatives (SPA + MSAL.js) et les
questions ouvertes à confirmer avant implémentation.
