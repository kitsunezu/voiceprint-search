"""Speaker management endpoints — list, rename, delete."""

import random

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_minio
from app.config import settings
from app.db import repository as repo
from app.storage.minio_client import delete_objects_by_prefix
from minio import Minio

router = APIRouter()


class SpeakerUpdate(BaseModel):
    name: str


@router.get("/speakers")
async def list_speakers(db: AsyncSession = Depends(get_db)):
    speakers = await repo.list_speakers(db)
    return {"speakers": speakers}


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
    deleted = await repo.delete_speaker(db, speaker_id)
    if not deleted:
        raise HTTPException(404, "Speaker not found")
    await db.commit()
    # Clean up all audio files stored under speakers/{speaker_id}/
    delete_objects_by_prefix(minio_client, f"speakers/{speaker_id}/")
    return Response(status_code=204)


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

    try:
        stat = minio_client.stat_object(settings.minio_bucket, asset.storage_key)
        total_size = stat.size

        range_header = request.headers.get("range", "")
        if range_header.startswith("bytes="):
            range_val = range_header[6:]
            parts = range_val.split("-", 1)
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else total_size - 1
            end = min(end, total_size - 1)
            length = end - start + 1

            obj = minio_client.get_object(
                settings.minio_bucket, asset.storage_key,
                offset=start, length=length,
            )
            data = obj.read()
            obj.close()
            obj.release_conn()
            return FastAPIResponse(
                content=data,
                status_code=206,
                media_type="audio/wav",
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
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(total_size),
            },
        )
    except Exception:
        raise HTTPException(500, "Failed to retrieve audio file")
