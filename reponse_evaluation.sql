-- Exécuter une fois sur la base terracogitia
CREATE TABLE IF NOT EXISTS reponse_evaluation (
    id_reponse_evaluation SERIAL PRIMARY KEY,
    id_theme INTEGER NOT NULL,
    id_subtheme INTEGER NOT NULL,
    id_question INTEGER NOT NULL,
    reponse TEXT NOT NULL,
    pertinence TEXT,
    pertinence_note INTEGER,
    precision_analyse TEXT,
    precision_note INTEGER,
    clarte TEXT,
    clarte_note INTEGER,
    synthese_points_forts TEXT[],
    synthese_points_faibles TEXT[],
    synthese_conseils_pedagogiques TEXT[],
    note INTEGER
);
