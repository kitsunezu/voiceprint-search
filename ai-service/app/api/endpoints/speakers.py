"""Speaker management endpoints — list, rename, delete."""

import logging
import mimetypes
import random

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_minio
from app.config import settings
from app.core.housekeep import (
    delete_object_if_exists,
    preview_audio_asset_delete,
    preview_speaker_delete,
    run_housekeep,
)
from app.db import repository as repo
from minio import Minio
from minio.error import S3Error

router = APIRouter()
logger = logging.getLogger(__name__)


class SpeakerCreate(BaseModel):
    name: str


class SpeakerUpdate(BaseModel):
    name: str


def _stream_audio_asset(
    *,
    asset,
    request: Request,
    minio_client: Minio,
) -> FastAPIResponse:
    try:
        stat = minio_client.stat_object(settings.minio_bucket, asset.storage_key)
        total_size = stat.size
        media_type = getattr(stat, "content_type", None) or mimetypes.guess_type(asset.original_filename)[0] or "application/octet-stream"

        range_header = request.headers.get("range", "")
        if range_header.startswith("bytes="):
            range_val = range_header[6:]
            parts = range_val.split("-", 1)
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else total_size - 1
            end = min(end, total_size - 1)
            length = end - start + 1

            obj = minio_client.get_object(
                settings.minio_bucket,
                asset.storage_key,
                offset=start,
                length=length,
            )
            data = obj.read()
            obj.close()
            obj.release_conn()
            return FastAPIResponse(
                content=data,
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                },
            )

        obj = minio_client.get_object(settings.minio_bucket, asset.storage_key)
        data = obj.read()
        obj.close()
        obj.release_conn()
        return FastAPIResponse(
            content=data,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(total_size),
            },
        )
    except Exception:
        logger.exception("Failed to retrieve audio file for asset=%s", getattr(asset, "id", "?"))
        raise HTTPException(500, "Failed to retrieve audio file")


@router.get("/speakers")
async def list_speakers(db: AsyncSession = Depends(get_db)):
    speakers = await repo.list_speakers(db)
    return {"speakers": speakers}


@router.post("/speakers/housekeep")
async def housekeep_speakers(
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    try:
        return await run_housekeep(db, minio_client)
    except S3Error:
        logger.exception("Failed to inspect MinIO objects during housekeeping")
        raise HTTPException(502, "Failed to inspect MinIO objects during housekeeping")


@router.post("/speakers", status_code=201)
async def create_speaker(
    body: SpeakerCreate,
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name cannot be empty")

    speaker = await repo.create_speaker(db, name=name)
    await db.commit()
    return {
        "id": speaker.id,
        "name": speaker.name,
        "description": speaker.description,
        "created_at": speaker.created_at.isoformat(),
        "embedding_count": 0,
        "embedded_audio_count": 0,
        "raw_audio_count": 0,
        "pending_audio_count": 0,
        "running_audio_count": 0,
        "failed_audio_count": 0,
        "no_speech_audio_count": 0,
        "succeeded_audio_count": 0,
    }


@router.get("/speakers/{speaker_id}")
async def get_speaker(speaker_id: int, db: AsyncSession = Depends(get_db)):
    speaker = await repo.get_speaker(db, speaker_id)
    if not speaker:
        raise HTTPException(404, "Speaker not found")
    embeddings = await repo.get_speaker_embeddings(db, speaker_id)
    return {
        "id": speaker.id,
        "name": speaker.name,
        "description": speaker.description,
        "created_at": speaker.created_at.isoformat(),
        "embedding_count": len(embeddings),
    }


@router.patch("/speakers/{speaker_id}")
async def update_speaker(
    speaker_id: int,
    body: SpeakerUpdate,
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name cannot be empty")
    speaker = await repo.update_speaker_name(db, speaker_id, name)
    if not speaker:
        raise HTTPException(404, "Speaker not found")
    await db.commit()
    return {"id": speaker.id, "name": speaker.name}


@router.delete("/speakers/{speaker_id}", status_code=204)
async def delete_speaker(
    speaker_id: int,
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    storage_keys = await repo.delete_speaker(db, speaker_id)
    if storage_keys is None:
        raise HTTPException(404, "Speaker not found")

    try:
        for object_name in storage_keys:
            delete_object_if_exists(minio_client, object_name)
        for obj in minio_client.list_objects(settings.minio_bucket, prefix=f"speakers/{speaker_id}/", recursive=True):
            delete_object_if_exists(minio_client, obj.object_name)
    except S3Error:
        await db.rollback()
        logger.exception("Failed to delete MinIO objects for speaker=%d", speaker_id)
        raise HTTPException(502, "Failed to delete speaker audio from MinIO")

    await db.commit()
    return Response(status_code=204)


@router.get("/speakers/{speaker_id}/delete-preview")
async def get_speaker_delete_preview(
    speaker_id: int,
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    try:
        preview = await preview_speaker_delete(db, minio_client, speaker_id)
    except S3Error:
        logger.exception("Failed to inspect MinIO objects for speaker delete preview=%d", speaker_id)
        raise HTTPException(502, "Failed to inspect MinIO objects")

    if not preview:
        raise HTTPException(404, "Speaker not found")
    return preview


@router.get("/speakers/{speaker_id}/audio-assets")
async def list_speaker_audio_assets(
    speaker_id: int,
    db: AsyncSession = Depends(get_db),
):
    speaker = await repo.get_speaker(db, speaker_id)
    if not speaker:
        raise HTTPException(404, "Speaker not found")

    assets = await repo.list_speaker_audio_asset_summaries(db, speaker_id)
    return {"audio_assets": assets}


@router.delete("/speakers/{speaker_id}/audio-assets/{asset_id}")
async def delete_speaker_audio_asset(
    speaker_id: int,
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    asset = await repo.get_speaker_audio_asset(db, speaker_id, asset_id)
    if not asset:
        raise HTTPException(404, "Audio asset not found")

    deleted_embeddings = await repo.count_embeddings_for_audio_asset(db, asset.id)
    object_deleted = False
    try:
        object_deleted = delete_object_if_exists(minio_client, asset.storage_key)
    except S3Error:
        logger.exception("Failed to delete audio asset from MinIO asset=%d key=%s", asset.id, asset.storage_key)
        raise HTTPException(502, "Failed to delete audio file from MinIO")

    await repo.delete_audio_asset(db, asset.id)
    await db.commit()

    return {
        "audio_asset_id": asset.id,
        "deleted_embeddings": deleted_embeddings,
        "deleted_object": object_deleted,
    }


@router.get("/speakers/{speaker_id}/audio-assets/{asset_id}/delete-preview")
async def get_speaker_audio_asset_delete_preview(
    speaker_id: int,
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    try:
        preview = await preview_audio_asset_delete(db, minio_client, speaker_id, asset_id)
    except S3Error:
        logger.exception(
            "Failed to inspect MinIO object for asset delete preview speaker=%d asset=%d",
            speaker_id,
            asset_id,
        )
        raise HTTPException(502, "Failed to inspect MinIO objects")

    if not preview:
        raise HTTPException(404, "Audio asset not found")
    return preview


@router.get("/speakers/{speaker_id}/audio")
async def get_speaker_audio(
    speaker_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    """Return a randomly selected audio sample, with HTTP Range (seek) support."""
    assets = await repo.get_speaker_audio_assets(db, speaker_id)
    if not assets:
        raise HTTPException(404, "No audio available for this speaker")

    asset = random.choice(assets)

    return _stream_audio_asset(asset=asset, request=request, minio_client=minio_client)


@router.get("/speakers/{speaker_id}/audio-assets/{asset_id}/audio")
async def get_speaker_audio_asset(
    speaker_id: int,
    asset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    asset = await repo.get_speaker_audio_asset(db, speaker_id, asset_id)
    if not asset:
        raise HTTPException(404, "Audio asset not found")

    return _stream_audio_asset(asset=asset, request=request, minio_client=minio_client)
