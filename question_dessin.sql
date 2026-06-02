-- Dessin Fabric.js associé à une question (réponse graphique).
ALTER TABLE question ADD COLUMN IF NOT EXISTS dessin JSONB;
