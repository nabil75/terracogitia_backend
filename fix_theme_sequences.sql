-- Réaligne les séquences sur le MAX(id) existant (corrige theme_pkey, subtheme_pkey, etc.)
-- après import SQL, restauration, ou INSERT avec id explicite.
--
-- Le 3e argument true (is_called) garantit que le prochain nextval sera MAX+1,
-- et non une réutilisation de MAX (erreur « valeur d'une clé dupliquée »).
--
-- Exemple : psql -U ... -d terracogitia -f fix_theme_sequences.sql

SELECT setval(
    pg_get_serial_sequence('public.theme', 'id_theme'),
    COALESCE((SELECT MAX(id_theme) FROM public.theme), 0),
    true
);

SELECT setval(
    pg_get_serial_sequence('public.subtheme', 'id_subtheme'),
    COALESCE((SELECT MAX(id_subtheme) FROM public.subtheme), 0),
    true
);

-- Décommenter si la table existe chez vous :
-- SELECT setval(
--     pg_get_serial_sequence('public.question', 'id_question'),
--     COALESCE((SELECT MAX(id_question) FROM public.question), 0),
--     true
-- );

-- SELECT setval(
--     pg_get_serial_sequence('public.evaluation', 'id_evaluation'),
--     COALESCE((SELECT MAX(id_evaluation) FROM public.evaluation), 0),
--     true
-- );

-- SELECT setval(
--     pg_get_serial_sequence('public.reponse_evaluation', 'id_reponse_evaluation'),
--     COALESCE((SELECT MAX(id_reponse_evaluation) FROM public.reponse_evaluation), 0),
--     true
-- );
