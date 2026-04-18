-- Migration 001: Support multi-model embeddings (different vector dimensions)
--
-- Run this against an existing voiceprint database that was created with the
-- original init.sql (vector(192) fixed-dimension column).
--
-- This migration:
--   1. Removes the fixed-dimension constraint so vectors of any size can coexist.
--   2. Adds an embedding_dim column for efficient per-model filtering.
--   3. Backfills embedding_dim for existing rows.
--   4. Drops the old IVFFlat index (requires fixed dimension).

BEGIN;

-- 1. Remove dimension constraint.  pgvector stores dimension per-row, so
--    existing 192-dim data stays intact.
ALTER TABLE embeddings ALTER COLUMN vector TYPE vector;

-- 2. Add dimension tracking column.
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS embedding_dim INTEGER;
UPDATE embeddings SET embedding_dim = 192 WHERE embedding_dim IS NULL;
ALTER TABLE embeddings ALTER COLUMN embedding_dim SET NOT NULL;
ALTER TABLE embeddings ALTER COLUMN embedding_dim SET DEFAULT 192;

-- 3. Drop old IVFFlat index (requires fixed dimension; no longer compatible).
DROP INDEX IF EXISTS idx_embeddings_vector;

-- 4. Add a standard btree index on model_version + embedding_dim for fast filtering.
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings (model_version, embedding_dim);

COMMIT;
