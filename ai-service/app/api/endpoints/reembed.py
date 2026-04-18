"""Re-embed all existing audio assets for all currently loaded models.

POST /api/v1/reembed

Iterates every AudioAsset row, downloads the original file from MinIO,
runs the mandatory preprocessing pipeline + each loaded embedder, and
inserts any missing Embedding rows.  Useful after adding a new model or
switching default models.
"""

import logging
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_embedder_registry, get_minio, get_preprocessor
from app.config import settings
from app.core.embedder import EmbedderRegistry, embed_segments
from app.core.preprocessing import AudioPreprocessor, PreprocessError
from app.db import repository as repo
from app.db.models import AudioAsset, Embedding
from minio import Minio

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/reembed")
async def reembed_all(
    db: AsyncSession = Depends(get_db),
    registry: EmbedderRegistry = Depends(get_embedder_registry),
    minio_client: Minio = Depends(get_minio),
    preprocessor: AudioPreprocessor = Depends(get_preprocessor),
):
    """Compute and store missing embeddings for every audio asset × loaded model."""
    counts = {"created": 0, "skipped": 0, "errors": 0}

    stmt = select(AudioAsset).where(AudioAsset.speaker_id.isnot(None))
    assets = list((await db.execute(stmt)).scalars().all())

    for asset in assets:
        existing_stmt = select(Embedding.model_version).where(
            Embedding.audio_asset_id == asset.id
        )
        existing = set((await db.execute(existing_stmt)).scalars().all())

        missing = [mid for mid in registry.available_ids if mid not in existing]
        if not missing:
            counts["skipped"] += 1
            continue

        tmp_dir = tempfile.mkdtemp()
        cleanup_dirs: list[str] = []
        try:
            tmp_path = os.path.join(tmp_dir, "audio.orig")
            minio_client.fget_object(settings.minio_bucket, asset.storage_key, tmp_path)

            try:
                result, pp_dirs = preprocessor.process(tmp_path)
            except PreprocessError:
                logger.warning("reembed: asset=%d — no usable speech, skipping", asset.id)
                counts["errors"] += 1
                continue
            cleanup_dirs.extend(pp_dirs)

            for mid in missing:
                try:
                    vec = embed_segments(registry.get(mid), result.segments)
                    await repo.create_embedding(
                        db,
                        speaker_id=asset.speaker_id,
                        audio_asset_id=asset.id,
                        vector=vec,
                        model_version=mid,
                    )
                    counts["created"] += 1
                    logger.info("reembed: asset=%d model=%s OK", asset.id, mid)
                except Exception:
                    logger.exception("reembed: asset=%d model=%s FAILED", asset.id, mid)
                    counts["errors"] += 1

        except Exception:
            logger.exception("reembed: failed to process asset %d", asset.id)
            counts["errors"] += 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            for d in cleanup_dirs:
                shutil.rmtree(d, ignore_errors=True)

    await db.commit()
    return counts
