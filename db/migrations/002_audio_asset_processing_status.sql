BEGIN;

ALTER TABLE audio_assets ADD COLUMN IF NOT EXISTS processing_status VARCHAR(32);
ALTER TABLE audio_assets ADD COLUMN IF NOT EXISTS processing_error TEXT;
ALTER TABLE audio_assets ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;
ALTER TABLE audio_assets ADD COLUMN IF NOT EXISTS processing_finished_at TIMESTAMPTZ;

UPDATE audio_assets
SET processing_status = CASE
    WHEN EXISTS (
        SELECT 1
        FROM embeddings e
        WHERE e.audio_asset_id = audio_assets.id
    ) THEN 'succeeded'
    WHEN has_speech = FALSE THEN 'no_speech'
    ELSE 'pending'
END
WHERE processing_status IS NULL;

UPDATE audio_assets
SET processing_finished_at = created_at
WHERE processing_finished_at IS NULL
  AND processing_status IN ('succeeded', 'no_speech');

ALTER TABLE audio_assets ALTER COLUMN processing_status SET NOT NULL;
ALTER TABLE audio_assets ALTER COLUMN processing_status SET DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_audio_assets_processing_status ON audio_assets (processing_status);

COMMIT;