-- Libellé textuel de la famille (clé JSON Mistral « libelle » par famille).
-- Colonne attendue : question.libelle_groupe

ALTER TABLE question
    ADD COLUMN IF NOT EXISTS libelle_groupe TEXT;

COMMENT ON COLUMN question.libelle_groupe IS
    'Libellé de la famille (POST /themes/regroupement_questions_parcours).';

-- Si une ancienne colonne groupe_libelle existe, copie optionnelle puis suppression manuelle :
-- UPDATE question SET libelle_groupe = groupe_libelle WHERE libelle_groupe IS NULL AND groupe_libelle IS NOT NULL;
-- ALTER TABLE question DROP COLUMN IF EXISTS groupe_libelle;
