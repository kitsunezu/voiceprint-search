BEGIN;

ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS window_index INTEGER;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS window_start_seconds REAL;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS window_duration_seconds REAL;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS speech_seconds REAL;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS weight REAL;

UPDATE embeddings
SET weight = 1.0
WHERE weight IS NULL;

ALTER TABLE embeddings ALTER COLUMN weight SET NOT NULL;
ALTER TABLE embeddings ALTER COLUMN weight SET DEFAULT 1.0;

CREATE INDEX IF NOT EXISTS idx_embeddings_asset_model_window
ON embeddings (audio_asset_id, model_version, window_index);

COMMIT;