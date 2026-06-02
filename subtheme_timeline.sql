-- Colonne de persistance de la séquence d'apprentissage (timeline) par parcours.
ALTER TABLE subtheme ADD COLUMN IF NOT EXISTS timeline JSONB;
