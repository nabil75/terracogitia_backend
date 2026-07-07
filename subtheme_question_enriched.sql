-- Parcours (sous-thèmes / domaines), thèmes et questions enrichis (génération IA / pyramide des savoirs).

-- Les clés JSON Mistral correspondent aux noms de colonnes ci-dessous.



ALTER TABLE theme ADD COLUMN IF NOT EXISTS role_cognitif TEXT;

ALTER TABLE theme ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT;

ALTER TABLE theme ADD COLUMN IF NOT EXISTS transformation_cognitive TEXT;

ALTER TABLE theme ADD COLUMN IF NOT EXISTS niveaux_secondaires JSONB;



ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS role_cognitif TEXT;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS transformations_cognitives JSONB;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS prerequis JSONB;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS ouvre_vers JSONB;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS niveaux_secondaires JSONB;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS profil_questions_attendu JSONB;

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS famille TEXT;



ALTER TABLE question ADD COLUMN IF NOT EXISTS objectif_pedagogique TEXT;

ALTER TABLE question ADD COLUMN IF NOT EXISTS concepts_vises JSONB;

ALTER TABLE question ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT;

ALTER TABLE question ADD COLUMN IF NOT EXISTS operation_cognitive TEXT;

ALTER TABLE question ADD COLUMN IF NOT EXISTS prerequis_concepts JSONB;

-- Consolidation : fusion de la colonne legacy `niveau_cognitif` dans `operation_cognitive`, puis suppression.
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


