-- Migration : colonne de regroupement des questions (famille 1…n après appel Mistral).
-- À exécuter une fois sur la base « terracogitia » si la colonne n'existe pas encore.

ALTER TABLE question
    ADD COLUMN IF NOT EXISTS groupe INTEGER;

COMMENT ON COLUMN question.groupe IS
    'Indice de famille (1…n) après regroupement IA des questions du parcours (POST /themes/regroupement_questions_parcours).';
