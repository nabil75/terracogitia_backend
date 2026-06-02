-- Parcours (sous-thèmes / domaines) et questions enrichis (génération IA).
-- Les clés JSON Mistral correspondent aux noms de colonnes ci-dessous.

ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT;
ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS role_cognitif TEXT;
ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS transformations_cognitives JSONB;
ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS prerequis JSONB;
ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS ouvre_vers JSONB;

ALTER TABLE question ADD COLUMN IF NOT EXISTS niveau_cognitif TEXT;
ALTER TABLE question ADD COLUMN IF NOT EXISTS objectif_pedagogique TEXT;
ALTER TABLE question ADD COLUMN IF NOT EXISTS concepts_vises JSONB;
