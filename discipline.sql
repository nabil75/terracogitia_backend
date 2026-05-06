-- Migration : introduit la notion de "discipline" (niveau au-dessus du thème).
-- A jouer une fois sur la base "terracogitia".
-- L'utilisateur dispose déjà de la table `discipline` (id_discipline / label / description) ;
-- ce script est idempotent et ne créera la table que si elle est absente.

CREATE TABLE IF NOT EXISTS discipline (
    id_discipline SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT
);

-- Lien thème → discipline (peut être NULL pour les thèmes encore non rattachés).
ALTER TABLE theme
    ADD COLUMN IF NOT EXISTS id_discipline INTEGER
    REFERENCES discipline(id_discipline) ON DELETE SET NULL;

-- Index pour accélérer le filtre sur GET /themes/all_themes?id_discipline=...
CREATE INDEX IF NOT EXISTS idx_theme_id_discipline
    ON theme (id_discipline);

-- Exemple de jeu de données initial (à adapter / supprimer si déjà saisi via l'interface) :
-- INSERT INTO discipline (label, description) VALUES
--     ('Intelligence artificielle', 'Tous les thèmes liés à l''IA et à l''apprentissage automatique'),
--     ('Informatique générale',     'Algorithmique, programmation, systèmes…'),
--     ('Sciences humaines',         'Pédagogie, philosophie, sociologie…');
