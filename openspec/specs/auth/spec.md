# Auth Specification

## Purpose
Gestion des comptes utilisateurs : création de compte, connexion et réinitialisation
de mot de passe. Le système est **stateless** : aucune session ni jeton n'est émis ;
la connexion n'est qu'une vérification d'identifiants. Toutes les autres routes de
l'API sont publiques (aucune dépendance d'authentification côté serveur).

Routes exposées sous le préfixe `/auth`. Table sous-jacente : `users`
(`id_user`, `email` unique, `hashed_password` bcrypt, `created_at`).
Les erreurs métier renvoient un `detail` structuré `{ code, message }` avec un `code`
parmi `email_not_found`, `invalid_password`, `email_already_exists`.

## Requirements

### Requirement: Inscription d'un utilisateur
Le système SHALL créer un compte via `POST /auth/register` à partir d'un email valide
et d'un mot de passe d'au moins 6 caractères, en stockant le mot de passe sous forme
de hash bcrypt, et SHALL empêcher la création de deux comptes avec le même email.

#### Scenario: Email disponible
- GIVEN un email absent de la table `users`
- WHEN un client envoie `POST /auth/register` avec `{ email, password }` (password ≥ 6)
- THEN la réponse est `200` avec `{ ok: true, id, email }`
- AND un enregistrement `users` est créé avec un `hashed_password` bcrypt

#### Scenario: Email déjà existant
- GIVEN un email déjà présent dans `users`
- WHEN un client envoie `POST /auth/register` avec cet email
- THEN la réponse est `409`
- AND `detail` vaut `{ code: "email_already_exists", message: "Un compte existe déjà avec cet email." }`

#### Scenario: Payload invalide
- GIVEN un email mal formé ou un mot de passe de moins de 6 caractères
- WHEN un client envoie `POST /auth/register`
- THEN la réponse est `422` (validation Pydantic)
- AND aucun compte n'est créé

### Requirement: Connexion sans session
Le système SHALL authentifier un utilisateur via `POST /auth/login` en vérifiant le
mot de passe contre le hash bcrypt, et SHALL renvoyer l'identité de l'utilisateur
**sans** créer de session, de cookie ni de jeton. Il n'existe aucune route de
déconnexion.

#### Scenario: Identifiants valides
- GIVEN un utilisateur existant avec un mot de passe correct
- WHEN un client envoie `POST /auth/login` avec `{ email, password }`
- THEN la réponse est `200` avec `{ ok: true, id, email }`
- AND aucun jeton ni cookie de session n'est renvoyé

#### Scenario: Email inconnu
- GIVEN un email absent de `users`
- WHEN un client envoie `POST /auth/login`
- THEN la réponse est `404` avec `detail.code = "email_not_found"`

#### Scenario: Mot de passe incorrect
- GIVEN un email existant et un mot de passe erroné
- WHEN un client envoie `POST /auth/login`
- THEN la réponse est `401` avec `detail = { code: "invalid_password", message: "Mot de passe incorrect." }`

### Requirement: Réinitialisation de mot de passe par email
Le système SHALL remplacer le mot de passe d'un compte via `POST /auth/reset_password`
en identifiant le compte par son email uniquement (sans preuve d'identité
supplémentaire) et en imposant un nouveau mot de passe d'au moins 6 caractères.

#### Scenario: Réinitialisation réussie
- GIVEN un utilisateur existant
- WHEN un client envoie `POST /auth/reset_password` avec `{ email, new_password }` (≥ 6)
- THEN la réponse est `200` avec `{ ok: true, email }`
- AND `hashed_password` est remplacé par le hash du nouveau mot de passe

#### Scenario: Email inconnu
- GIVEN un email absent de `users`
- WHEN un client envoie `POST /auth/reset_password`
- THEN la réponse est `404` avec `detail.code = "email_not_found"`

#### Scenario: Réinitialisation non protégée (contrainte observée)
- GIVEN un acteur connaissant seulement l'email d'un compte
- WHEN il envoie `POST /auth/reset_password` avec un nouveau mot de passe valide
- THEN le mot de passe est remplacé sans vérification d'email ni de mot de passe courant
- AND ceci constitue une réinitialisation ouverte par email (comportement actuel)
