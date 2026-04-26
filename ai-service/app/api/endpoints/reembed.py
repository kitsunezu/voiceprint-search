"""Queue background reprocessing for existing audio assets.

POST /api/v1/reembed

Deletes existing embeddings when overwrite mode is enabled, marks assets as
pending again, and re-queues the normal background audio processing worker for
each stored asset.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db import repository as repo
from app.db.models import AudioAsset, Embedding

logger = logging.getLogger(__name__)
router = APIRouter()


def _enqueue_background_asset_processing(asset_id: int) -> bool:
    try:
        from app.worker.tasks import process_audio_asset_embeddings

        process_audio_asset_embeddings.send(int(asset_id))
        return True
    except Exception:
        logger.exception("Failed to enqueue background processing for audio asset %d", asset_id)
        return False


@router.post("/reembed")
async def reembed_all(
    db: AsyncSession = Depends(get_db),
    overwrite: bool = True,
):
    """Queue background audio reprocessing for every enrolled audio asset."""
    counts = {"created": 0, "skipped": 0, "deleted": 0, "errors": 0}

    stmt = select(AudioAsset).where(AudioAsset.speaker_id.isnot(None))
    assets = list((await db.execute(stmt)).scalars().all())
    queued_asset_ids: list[int] = []

    for asset in assets:
        existing_stmt = select(Embedding.id).where(Embedding.audio_asset_id == asset.id)
        existing_ids = list((await db.execute(existing_stmt)).scalars().all())
        if not overwrite and existing_ids:
            counts["skipped"] += 1
            continue

        if overwrite and existing_ids:
            counts["deleted"] += await repo.delete_embeddings_for_audio_asset(db, asset_id=int(asset.id))

        asset.processing_status = "pending"
        asset.processing_error = None
        asset.processing_started_at = None
        asset.processing_finished_at = None
        queued_asset_ids.append(int(asset.id))

    await db.commit()

    failed_asset_ids: list[int] = []
    for asset_id in queued_asset_ids:
        if _enqueue_background_asset_processing(asset_id):
            counts["created"] += 1
        else:
            counts["errors"] += 1
            failed_asset_ids.append(asset_id)

    if failed_asset_ids:
        for asset_id in failed_asset_ids:
            asset = await db.get(AudioAsset, asset_id)
            if asset is None:
                continue
            asset.processing_status = "failed"
            asset.processing_error = "Background processing was not queued."
        await db.commit()

    return counts
