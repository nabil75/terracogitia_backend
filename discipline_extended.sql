-- Extension de l'entité discipline (champs pédagogiques + compétences / prérequis).

ALTER TABLE discipline ADD COLUMN IF NOT EXISTS tagline TEXT;
ALTER TABLE discipline ADD COLUMN IF NOT EXISTS niveau_estime TEXT;
ALTER TABLE discipline ADD COLUMN IF NOT EXISTS projection TEXT;

CREATE TABLE IF NOT EXISTS competence (
    id_competence SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    id_discipline INTEGER NOT NULL REFERENCES discipline(id_discipline) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prerequis (
    id_prerequis SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    id_discipline INTEGER NOT NULL REFERENCES discipline(id_discipline) ON DELETE CASCADE
);

ALTER TABLE competence ADD COLUMN IF NOT EXISTS id_discipline INTEGER
    REFERENCES discipline(id_discipline) ON DELETE CASCADE;

ALTER TABLE prerequis ADD COLUMN IF NOT EXISTS id_discipline INTEGER
    REFERENCES discipline(id_discipline) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_competence_discipline ON competence (id_discipline);
CREATE INDEX IF NOT EXISTS idx_prerequis_discipline ON prerequis (id_discipline);

-- Métadonnées cognitives des thèmes (génération IA à la création de discipline).
ALTER TABLE theme ADD COLUMN IF NOT EXISTS role_cognitif TEXT;
ALTER TABLE theme ADD COLUMN IF NOT EXISTS niveau_pyramide TEXT;
ALTER TABLE theme ADD COLUMN IF NOT EXISTS transformation_cognitive TEXT;
