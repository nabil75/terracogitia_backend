-- À exécuter une fois sur la base `terracogitia`
CREATE TABLE IF NOT EXISTS users (
    id_user SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Authentification Microsoft (OAuth 2.0 / OIDC) : liaison de compte par email.
-- `hashed_password` devient optionnel (comptes créés via Microsoft, sans mot de passe).
ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS azure_oid TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT DEFAULT 'local';
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Identifiant Microsoft (`oid`) unique lorsqu'il est renseigné.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_azure_oid
    ON users (azure_oid) WHERE azure_oid IS NOT NULL;
