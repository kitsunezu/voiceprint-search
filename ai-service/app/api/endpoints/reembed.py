"""Rebuild existing audio assets for all currently loaded models.

POST /api/v1/reembed

Iterates every AudioAsset row, downloads the original file from MinIO,
runs the long-form reference profile builder + each loaded embedder, and
recreates the Embedding rows for that asset when overwrite mode is enabled.
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
from app.core.embedder import EmbedderRegistry
from app.core.preprocessing import AudioPreprocessor
from app.core.reference_profiles import build_reference_profile, persist_reference_embeddings
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
    overwrite: bool = True,
):
    """Rebuild embeddings for every enrolled audio asset using windowed references."""
    counts = {"created": 0, "skipped": 0, "deleted": 0, "errors": 0}

    stmt = select(AudioAsset).where(AudioAsset.speaker_id.isnot(None))
    assets = list((await db.execute(stmt)).scalars().all())

    for asset in assets:
        existing_stmt = select(Embedding.id).where(Embedding.audio_asset_id == asset.id)
        existing_ids = list((await db.execute(existing_stmt)).scalars().all())
        if not overwrite and existing_ids:
            counts["skipped"] += 1
            continue

        tmp_dir = tempfile.mkdtemp()
        cleanup_dirs: list[str] = []
        try:
            tmp_path = os.path.join(tmp_dir, "audio.orig")
            minio_client.fget_object(settings.minio_bucket, asset.storage_key, tmp_path)

            profile_windows, pp_dirs, asset_duration_seconds = build_reference_profile(
                tmp_path,
                preprocessor=preprocessor,
                cfg=settings,
            )
            if not profile_windows:
                logger.warning("reembed: asset=%d — no usable speech, skipping", asset.id)
                counts["errors"] += 1
                continue
            cleanup_dirs.extend(pp_dirs)
            if asset_duration_seconds is not None:
                asset.duration_seconds = float(asset_duration_seconds)

            result = await persist_reference_embeddings(
                db,
                asset_id=asset.id,
                speaker_id=asset.speaker_id,
                available_models=registry.available_ids,
                registry=registry,
                profile_windows=profile_windows,
                overwrite=overwrite,
            )
            counts["created"] += int(result["created"])
            counts["errors"] += len(result["failures"])
            if overwrite:
                counts["deleted"] += len(existing_ids)
            if result["created"]:
                logger.info("reembed: asset=%d rebuilt %d embeddings", asset.id, int(result["created"]))
            else:
                counts["skipped"] += 1

        except Exception:
            logger.exception("reembed: failed to process asset %d", asset.id)
            counts["errors"] += 1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            for d in cleanup_dirs:
                shutil.rmtree(d, ignore_errors=True)

    await db.commit()
    return counts
