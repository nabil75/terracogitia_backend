import asyncpg

db_params = {
    "database": "terracogitia",
    "user": "postgres",
    "password": "nBl030130!",
    "host": "localhost",
    "port": "5432",
}

pool = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(**db_params)
    # Schéma attendu par POST /themes/regroupement_questions_parcours.
    async with pool.acquire() as conn:
        # Authentification Microsoft : colonnes de liaison de compte + mot de passe optionnel.
        await conn.execute(
            "ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL"
        )
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS azure_oid TEXT"
        )
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT DEFAULT 'local'"
        )
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT"
        )
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_azure_oid "
            "ON users (azure_oid) WHERE azure_oid IS NOT NULL"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS groupe INTEGER"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS libelle_groupe TEXT"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS timeline JSONB"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS role_cognitif TEXT"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS transformations_cognitives JSONB"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS prerequis JSONB"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS ouvre_vers JSONB"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS objectif_pedagogique TEXT"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS concepts_vises JSONB"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS dessin JSONB"
        )
        await conn.execute(
            "ALTER TABLE discipline ADD COLUMN IF NOT EXISTS tagline TEXT"
        )
        await conn.execute(
            "ALTER TABLE discipline ADD COLUMN IF NOT EXISTS niveau_estime TEXT"
        )
        await conn.execute(
            "ALTER TABLE discipline ADD COLUMN IF NOT EXISTS projection TEXT"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS competence (
                id_competence SERIAL PRIMARY KEY,
                label TEXT NOT NULL,
                id_discipline INTEGER NOT NULL
                    REFERENCES discipline(id_discipline) ON DELETE CASCADE
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prerequis (
                id_prerequis SERIAL PRIMARY KEY,
                label TEXT NOT NULL,
                id_discipline INTEGER NOT NULL
                    REFERENCES discipline(id_discipline) ON DELETE CASCADE
            )
            """
        )
        await conn.execute(
            "ALTER TABLE competence ADD COLUMN IF NOT EXISTS id_discipline INTEGER "
            "REFERENCES discipline(id_discipline) ON DELETE CASCADE"
        )
        await conn.execute(
            "ALTER TABLE prerequis ADD COLUMN IF NOT EXISTS id_discipline INTEGER "
            "REFERENCES discipline(id_discipline) ON DELETE CASCADE"
        )
        await conn.execute(
            "ALTER TABLE proposition ADD COLUMN IF NOT EXISTS statut_current BOOLEAN "
            "NOT NULL DEFAULT false"
        )
        await conn.execute(
            "ALTER TABLE proposition ADD COLUMN IF NOT EXISTS notes TEXT"
        )
        await conn.execute(
            "ALTER TABLE proposition ADD COLUMN IF NOT EXISTS date_creation TEXT"
        )
        await conn.execute(
            "ALTER TABLE theme ADD COLUMN IF NOT EXISTS role_cognitif TEXT"
        )
        await conn.execute(
            "ALTER TABLE theme ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT"
        )
        await conn.execute(
            "ALTER TABLE theme ADD COLUMN IF NOT EXISTS transformation_cognitive TEXT"
        )
        await conn.execute(
            "ALTER TABLE theme ADD COLUMN IF NOT EXISTS niveaux_secondaires JSONB"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS niveaux_secondaires JSONB"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS profil_questions_attendu JSONB"
        )
        await conn.execute(
            "ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS famille TEXT"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS operation_cognitive TEXT"
        )
        await conn.execute(
            "ALTER TABLE question ADD COLUMN IF NOT EXISTS prerequis_concepts JSONB"
        )
        # Consolidation : `niveau_cognitif` (legacy) fusionnée dans `operation_cognitive`
        # puis supprimée. Idempotent : ne s'exécute que si la colonne existe encore.
        await conn.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'question' AND column_name = 'niveau_cognitif'
                ) THEN
                    UPDATE question
                    SET operation_cognitive = niveau_cognitif
                    WHERE operation_cognitive IS NULL AND niveau_cognitif IS NOT NULL;
                    ALTER TABLE question DROP COLUMN niveau_cognitif;
                END IF;
            END $$;
            """
        )
        # Suppression des tables legacy d'évaluation par questions (remplacées par défis).
        await conn.execute("DROP TABLE IF EXISTS discover_activity CASCADE")
        await conn.execute("DROP TABLE IF EXISTS subtheme_session CASCADE")
        await conn.execute("DROP TABLE IF EXISTS evaluation CASCADE")
        await conn.execute("DROP TABLE IF EXISTS reponse_evaluation CASCADE")


async def close_db():
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def postgres_select_query(query, *params):
        conn = await asyncpg.connect(**db_params)
        values = await conn.fetch(query, *params)
        await conn.close()
        return values

async def postgres_select_count_query(query):
        conn = await asyncpg.connect(**db_params)
        row = await conn.fetchrow(query)
        await conn.close()
        return row[0]

async def postgres_insert_query(query, *params):
        conn = await asyncpg.connect(**db_params)
        last_id = await conn.fetchval(query, *params)
        await conn.close()
        return last_id


async def postgres_update_query(query, *params):
        conn = await asyncpg.connect(**db_params)
        await conn.execute(query, *params)
        await conn.close()
        return "Update query executed successfully."


async def postgres_delete_query(query, *params):
        conn = await asyncpg.connect(**db_params)
        await conn.execute(query, *params)
        await conn.close()
        return "Delete query executed successfully."
