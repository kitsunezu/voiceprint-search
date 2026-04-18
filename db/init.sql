-- Voiceprint Search database initialisation
-- Runs automatically on first PostgreSQL container start

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE speakers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audio_assets (
    id                  SERIAL PRIMARY KEY,
    speaker_id          INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
    original_filename   VARCHAR(512) NOT NULL,
    storage_key         VARCHAR(512) NOT NULL,
    duration_seconds    REAL,
    sample_rate         INTEGER,
    has_speech          BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE embeddings (
    id              SERIAL PRIMARY KEY,
    speaker_id      INTEGER NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    audio_asset_id  INTEGER NOT NULL REFERENCES audio_assets(id) ON DELETE CASCADE,
    vector          vector,          -- dimensionless; actual dim stored in embedding_dim
    model_version   VARCHAR(100) NOT NULL DEFAULT 'ecapa-tdnn-v1',
    embedding_dim   INTEGER NOT NULL DEFAULT 192,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- At ≤ 2 000 speakers × ~10 samples = ~20 k rows, exact cosine scan is fast.
-- Add IVFFlat / HNSW partial indexes per model when the table grows past ~100 k.
-- Example (uncomment when needed):
--   CREATE INDEX idx_emb_vec_ecapa ON embeddings
--       USING ivfflat (vector vector_cosine_ops) WITH (lists = 50)
--       WHERE model_version = 'ecapa-tdnn-v1' AND embedding_dim = 192;

-- Useful for per-speaker lookups
CREATE INDEX idx_embeddings_speaker ON embeddings (speaker_id);
CREATE INDEX idx_audio_assets_speaker ON audio_assets (speaker_id);
