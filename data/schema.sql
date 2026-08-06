PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS plants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    species             TEXT,
    species_confidence  REAL,
    location_kind       TEXT    NOT NULL CHECK (location_kind IN ('indoor', 'outdoor')),
    location_text       TEXT,
    acquired_at         TEXT,
    photo_ref           TEXT,
    created_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id    INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL CHECK (kind IN ('initial', 'recheck')),
    photo_refs  TEXT    NOT NULL,
    user_notes  TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id      INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    plant_id            INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    differential_json   TEXT    NOT NULL,
    primary_candidate   TEXT,
    primary_confidence  REAL,
    severity            TEXT,
    contagion_json      TEXT,
    retrieved_refs_json TEXT    NOT NULL,
    model               TEXT    NOT NULL,
    token_usage_json    TEXT,
    cost_usd            REAL,
    created_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS roadmap_steps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    diagnosis_id   INTEGER NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
    plant_id       INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    ordinal        INTEGER NOT NULL,
    action         TEXT    NOT NULL,
    rationale      TEXT    NOT NULL,
    success_signal TEXT    NOT NULL,
    tier           INTEGER NOT NULL,
    due_date       TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'done', 'skipped')),
    completed_at   TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    diagnosis_id INTEGER NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
    rating       INTEGER CHECK (rating BETWEEN 1 AND 5),
    did_it_help  TEXT    CHECK (did_it_help IN ('yes', 'no', 'unclear', 'too_early')),
    free_text    TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profile (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fact           TEXT    NOT NULL UNIQUE,
    source         TEXT    NOT NULL CHECK (source IN ('inferred', 'stated')),
    confidence     REAL    NOT NULL,
    first_seen     TEXT    NOT NULL,
    last_confirmed TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id        INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         TEXT    NOT NULL,
    tool_calls_json TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_plant ON observations(plant_id);
CREATE INDEX IF NOT EXISTS idx_diagnoses_plant    ON diagnoses(plant_id);
CREATE INDEX IF NOT EXISTS idx_roadmap_plant      ON roadmap_steps(plant_id);
CREATE INDEX IF NOT EXISTS idx_roadmap_status     ON roadmap_steps(status, due_date);
CREATE INDEX IF NOT EXISTS idx_messages_plant     ON messages(plant_id, created_at);
