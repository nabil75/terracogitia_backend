-- Évaluation avancée : sessions parcours (Discover) et journal d'activité.

CREATE TABLE IF NOT EXISTS subtheme_session (
    id_session SERIAL PRIMARY KEY,
    id_theme INTEGER,
    id_subtheme INTEGER NOT NULL,
    entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exited_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    source TEXT NOT NULL DEFAULT 'discover'
);

CREATE INDEX IF NOT EXISTS idx_subtheme_session_subtheme
    ON subtheme_session (id_subtheme);
CREATE INDEX IF NOT EXISTS idx_subtheme_session_entered
    ON subtheme_session (entered_at DESC);

CREATE TABLE IF NOT EXISTS discover_activity (
    id_activity SERIAL PRIMARY KEY,
    id_theme INTEGER,
    id_subtheme INTEGER,
    id_question INTEGER,
    event_type TEXT NOT NULL,
    id_proposition INTEGER,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discover_activity_subtheme
    ON discover_activity (id_subtheme);
CREATE INDEX IF NOT EXISTS idx_discover_activity_created
    ON discover_activity (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_discover_activity_event
    ON discover_activity (event_type);
