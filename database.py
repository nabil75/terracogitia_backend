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
        # Thèmes : suppression en cascade quand la discipline est supprimée (remplace SET NULL).
        await conn.execute(
            """
            DO $$
            DECLARE
                fk_name TEXT;
            BEGIN
                SELECT tc.constraint_name INTO fk_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = 'theme'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'id_discipline'
                LIMIT 1;

                IF fk_name IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE theme DROP CONSTRAINT %I', fk_name);
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_schema = 'public'
                      AND table_name = 'theme'
                      AND constraint_name = 'theme_id_discipline_fkey'
                ) THEN
                    ALTER TABLE theme
                        ADD CONSTRAINT theme_id_discipline_fkey
                        FOREIGN KEY (id_discipline)
                        REFERENCES discipline(id_discipline)
                        ON DELETE CASCADE;
                END IF;
            END $$;
            """
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
        # Compétences / prérequis : CASCADE sur suppression de discipline (bases existantes).
        await conn.execute(
            """
            DO $$
            DECLARE
                fk_name TEXT;
                rec RECORD;
            BEGIN
                FOR rec IN
                    SELECT *
                    FROM (
                        VALUES
                            ('competence', 'competence_id_discipline_fkey'),
                            ('prerequis', 'prerequis_id_discipline_fkey')
                    ) AS t(table_name, constraint_name)
                LOOP
                    SELECT tc.constraint_name INTO fk_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.referential_constraints rc
                      ON rc.constraint_name = tc.constraint_name
                     AND rc.constraint_schema = tc.table_schema
                    WHERE tc.table_schema = 'public'
                      AND tc.table_name = rec.table_name
                      AND tc.constraint_type = 'FOREIGN KEY'
                      AND kcu.column_name = 'id_discipline'
                    LIMIT 1;

                    IF fk_name IS NOT NULL THEN
                        IF fk_name = rec.constraint_name THEN
                            IF EXISTS (
                                SELECT 1
                                FROM information_schema.referential_constraints rc
                                WHERE rc.constraint_schema = 'public'
                                  AND rc.constraint_name = fk_name
                                  AND rc.delete_rule = 'CASCADE'
                            ) THEN
                                CONTINUE;
                            END IF;
                        END IF;
                        EXECUTE format(
                            'ALTER TABLE %I DROP CONSTRAINT %I',
                            rec.table_name,
                            fk_name
                        );
                    END IF;

                    EXECUTE format(
                        'ALTER TABLE %I ADD CONSTRAINT %I '
                        'FOREIGN KEY (id_discipline) REFERENCES discipline(id_discipline) '
                        'ON DELETE CASCADE',
                        rec.table_name,
                        rec.constraint_name
                    );
                END LOOP;
            END $$;
            """
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

        # --- Cadre d'évaluation par défis cognitifs ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_operation_catalog (
                operation_key TEXT PRIMARY KEY,
                family TEXT NOT NULL,
                label_fr TEXT NOT NULL,
                label_en TEXT NOT NULL,
                definition_fr TEXT NOT NULL,
                definition_en TEXT NOT NULL,
                evaluates_fr TEXT NOT NULL,
                evaluates_en TEXT NOT NULL,
                pyramid_levels JSONB NOT NULL DEFAULT '[]'::jsonb,
                examples JSONB NOT NULL DEFAULT '[]'::jsonb
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_mechanic_catalog (
                mechanic_key TEXT PRIMARY KEY,
                label_fr TEXT NOT NULL,
                label_en TEXT NOT NULL,
                description_fr TEXT NOT NULL,
                description_en TEXT NOT NULL,
                advantages_fr TEXT NOT NULL,
                limitations_fr TEXT NOT NULL,
                compatible_operations JSONB NOT NULL DEFAULT '[]'::jsonb,
                compatible_pyramid_levels JSONB NOT NULL DEFAULT '[]'::jsonb
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_mechanic_compatibility (
                operation_key TEXT NOT NULL REFERENCES cognitive_operation_catalog(operation_key),
                mechanic_key TEXT NOT NULL REFERENCES game_mechanic_catalog(mechanic_key),
                score INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (operation_key, mechanic_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_challenge (
                id_challenge SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                pyramid_level TEXT NOT NULL,
                cognitive_operation TEXT NOT NULL,
                game_mechanic TEXT NOT NULL,
                knowledge_object_type TEXT NOT NULL DEFAULT 'question',
                knowledge_object_id INTEGER NOT NULL,
                difficulty INTEGER NOT NULL DEFAULT 2,
                success_criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
                evaluated_competencies JSONB NOT NULL DEFAULT '[]'::jsonb,
                prerequisites JSONB NOT NULL DEFAULT '[]'::jsonb,
                typical_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
                performance_indicators JSONB NOT NULL DEFAULT '[]'::jsonb,
                generation_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
                content_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS challenge_exercise (
                id_exercise SERIAL PRIMARY KEY,
                id_challenge INTEGER REFERENCES cognitive_challenge(id_challenge) ON DELETE SET NULL,
                id_user INTEGER,
                knowledge_object_type TEXT NOT NULL,
                knowledge_object_id INTEGER NOT NULL,
                pyramid_level TEXT NOT NULL,
                cognitive_operation TEXT NOT NULL,
                game_mechanic TEXT NOT NULL,
                difficulty INTEGER NOT NULL DEFAULT 2,
                content JSONB NOT NULL DEFAULT '{}'::jsonb,
                success_criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
                status TEXT NOT NULL DEFAULT 'ready',
                compatibility_score INTEGER,
                is_first_for_question BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS challenge_attempt (
                id_attempt SERIAL PRIMARY KEY,
                id_exercise INTEGER NOT NULL REFERENCES challenge_exercise(id_exercise) ON DELETE CASCADE,
                id_user INTEGER,
                attempt_number INTEGER NOT NULL DEFAULT 1,
                learner_actions JSONB NOT NULL DEFAULT '{}'::jsonb,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                score DOUBLE PRECISION NOT NULL DEFAULT 0,
                mastery_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
                error_patterns JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS challenge_evaluation (
                id_evaluation SERIAL PRIMARY KEY,
                id_attempt INTEGER NOT NULL REFERENCES challenge_attempt(id_attempt) ON DELETE CASCADE,
                criteria_results JSONB NOT NULL DEFAULT '{}'::jsonb,
                competency_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
                feedback JSONB NOT NULL DEFAULT '{}'::jsonb,
                passed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learner_mastery (
                id_mastery SERIAL PRIMARY KEY,
                id_user INTEGER NOT NULL,
                knowledge_object_type TEXT NOT NULL,
                knowledge_object_id INTEGER NOT NULL,
                pyramid_level TEXT NOT NULL,
                cognitive_operation TEXT NOT NULL,
                mastery_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TIMESTAMPTZ,
                UNIQUE (id_user, knowledge_object_type, knowledge_object_id, pyramid_level, cognitive_operation)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learner_gamification (
                id_user INTEGER PRIMARY KEY,
                xp_total INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                streak_days INTEGER NOT NULL DEFAULT 0,
                last_activity_at TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS achievement_definition (
                achievement_key TEXT PRIMARY KEY,
                title_fr TEXT NOT NULL,
                title_en TEXT NOT NULL,
                description_fr TEXT NOT NULL,
                description_en TEXT NOT NULL,
                criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
                xp_reward INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learner_achievement (
                id_user INTEGER NOT NULL,
                achievement_key TEXT NOT NULL REFERENCES achievement_definition(achievement_key),
                unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (id_user, achievement_key)
            )
            """
        )
        await conn.execute(
            "ALTER TABLE challenge_exercise ADD COLUMN IF NOT EXISTS compatibility_score INTEGER"
        )
        await conn.execute(
            "ALTER TABLE challenge_exercise ADD COLUMN IF NOT EXISTS is_first_for_question BOOLEAN NOT NULL DEFAULT FALSE"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_reservoir (
                id_record SERIAL PRIMARY KEY,
                id_user INTEGER,
                knowledge_object_type TEXT NOT NULL,
                knowledge_object_id INTEGER NOT NULL,
                pyramid_level TEXT NOT NULL,
                cognitive_operation TEXT NOT NULL,
                game_mechanic TEXT NOT NULL,
                compatibility_score INTEGER NOT NULL DEFAULT 0,
                is_first_challenge BOOLEAN NOT NULL DEFAULT FALSE,
                id_exercise INTEGER REFERENCES challenge_exercise(id_exercise) ON DELETE SET NULL,
                id_attempt INTEGER REFERENCES challenge_attempt(id_attempt) ON DELETE SET NULL,
                id_evaluation INTEGER REFERENCES challenge_evaluation(id_evaluation) ON DELETE SET NULL,
                score DOUBLE PRECISION NOT NULL DEFAULT 0,
                passed BOOLEAN NOT NULL DEFAULT FALSE,
                xp_gained INTEGER NOT NULL DEFAULT 0,
                mastery_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                feedback JSONB NOT NULL DEFAULT '{}'::jsonb,
                criteria_results JSONB NOT NULL DEFAULT '{}'::jsonb,
                dashboard_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_reservoir_user_object
            ON evaluation_reservoir (id_user, knowledge_object_type, knowledge_object_id)
            """
        )

        from challenge_framework.seed_db import seed_challenge_catalog
        await seed_challenge_catalog(conn)


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
