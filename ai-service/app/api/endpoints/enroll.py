"""Speaker enroll endpoint — register a new speaker with an audio sample."""

import asyncio
import logging
import os
import re
import shutil
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_minio
from app.core.audio import validate_extension
from app.core.enroll_jobs import (
    complete_enroll_job,
    create_enroll_job,
    fail_enroll_job,
    get_enroll_job,
    get_redis_client,
    load_enroll_job_payload,
    mark_enroll_job_running,
    store_enroll_job_payload,
    update_enroll_job,
)
from app.db import repository as repo
from app.storage.minio_client import upload_file
from minio import Minio

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_audio_object_key(speaker_id: int, original_filename: str, unique_token: str) -> str:
    file_name = original_filename or "audio.wav"
    ext = os.path.splitext(file_name)[1] or ".wav"
    stem = os.path.splitext(file_name)[0]
    stem = re.sub(r'[/\\\u29f8\u2044\u2215\x00-\x1f\x7f]+', '-', stem).strip(' -')
    prefix = f"{unique_token}_"
    max_stem_bytes = 250 - len(prefix.encode()) - len(ext.encode())
    stem_encoded = stem.encode("utf-8")
    if len(stem_encoded) > max_stem_bytes:
        stem_encoded = stem_encoded[:max_stem_bytes]
        stem = stem_encoded.decode("utf-8", errors="ignore").rstrip()
    safe_name = f"{prefix}{stem or 'audio'}{ext}"
    return f"speakers/{speaker_id}/{safe_name}"


def _enqueue_background_asset_processing(asset_id: int) -> bool:
    try:
        from app.worker.tasks import process_audio_asset_embeddings

        process_audio_asset_embeddings.send(int(asset_id))
        return True
    except Exception:
        logger.exception("Failed to enqueue background processing for audio asset %d", asset_id)
        return False


async def _resolve_speaker(
    *,
    db: AsyncSession,
    speaker_id: int | None,
    speaker_name: str,
) -> tuple[int, str]:
    cleaned_name = speaker_name.strip()
    if speaker_id is not None:
        speaker = await repo.get_speaker(db, speaker_id)
        if not speaker:
            raise HTTPException(404, f"Speaker ID {speaker_id} not found")
        return int(speaker.id), cleaned_name or speaker.name

    if not cleaned_name:
        raise HTTPException(400, "speaker_name is required when speaker_id is not provided")

    speaker = await repo.create_speaker(db, name=cleaned_name)
    await db.commit()
    return int(speaker.id), speaker.name


async def _store_audio_asset(
    *,
    db: AsyncSession,
    speaker_id: int,
    speaker_name: str,
    original_filename: str,
    object_key: str,
) -> dict:
    speaker = await repo.get_speaker(db, speaker_id)
    if not speaker:
        raise HTTPException(404, f"Speaker ID {speaker_id} not found")

    asset = await repo.create_audio_asset(
        db,
        speaker_id=speaker.id,
        original_filename=original_filename or "audio.wav",
        storage_key=object_key,
    )
    await db.commit()

    background_queued = _enqueue_background_asset_processing(int(asset.id))
    message_name = speaker_name or speaker.name
    if background_queued:
        message = f"Stored raw audio for speaker '{message_name}'. Background processing queued."
    else:
        message = f"Stored raw audio for speaker '{message_name}'. Background processing was not queued."

    return {
        "speaker_id": int(speaker.id),
        "audio_asset_id": int(asset.id),
        "processing_queued": background_queued,
        "message": message,
    }


async def _finalize_enroll_job(redis_client, job_id: str, payload: dict, db: AsyncSession) -> dict:
    speaker_id_raw = payload.get("speaker_id")
    object_key = str(payload.get("object_key") or "").strip()
    original_filename = str(payload.get("original_filename") or "audio.wav")
    speaker_name = str(payload.get("speaker_name") or "").strip()

    if speaker_id_raw is None:
        fail_enroll_job(redis_client, job_id, error="speaker_id is required")
        raise HTTPException(400, "speaker_id is required")
    if not object_key:
        fail_enroll_job(redis_client, job_id, error="object_key is required")
        raise HTTPException(400, "object_key is required")

    mark_enroll_job_running(redis_client, job_id, stage="persist", progress=60)

    try:
        result = await _store_audio_asset(
            db=db,
            speaker_id=int(speaker_id_raw),
            speaker_name=speaker_name,
            original_filename=original_filename,
            object_key=object_key,
        )
    except HTTPException as exc:
        fail_enroll_job(redis_client, job_id, error=str(exc.detail))
        raise
    except Exception as exc:
        logger.exception("Failed to finalize enroll job %s", job_id)
        fail_enroll_job(redis_client, job_id, error=str(exc))
        raise HTTPException(500, "Failed to store uploaded audio")

    completed = complete_enroll_job(redis_client, job_id, result=result)
    return completed or result


@router.post("/enroll", status_code=201)
async def enroll_speaker(
    audio: UploadFile = File(...),
    speaker_name: str = Form(...),
    speaker_id: int | None = Form(None),
    model: str = Form(""),
    # separate_vocals kept for backward compat but ignored — always True now
    separate_vocals: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    minio_client: Minio = Depends(get_minio),
):
    del model, separate_vocals

    if not audio.filename or not validate_extension(audio.filename):
        raise HTTPException(400, "Unsupported audio format")

    tmp_dir = tempfile.mkdtemp()
    try:
        ext = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
        raw_path = os.path.join(tmp_dir, f"raw_{uuid.uuid4().hex[:8]}{ext}")
        with open(raw_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        resolved_speaker_id, resolved_speaker_name = await _resolve_speaker(
            db=db,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        object_key = _build_audio_object_key(resolved_speaker_id, audio.filename, uuid.uuid4().hex[:8])
        await asyncio.to_thread(
            upload_file,
            minio_client,
            object_key,
            raw_path,
            content_type=audio.content_type or "application/octet-stream",
        )

        return await _store_audio_asset(
            db=db,
            speaker_id=resolved_speaker_id,
            speaker_name=resolved_speaker_name,
            original_filename=audio.filename or "audio.wav",
            object_key=object_key,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/enroll/jobs", status_code=202)
async def create_enroll_job_endpoint(
    audio: UploadFile = File(...),
    speaker_name: str = Form(...),
    speaker_id: int | None = Form(None),
    model: str = Form(""),
    auto_start: bool = Form(True),
    minio_client: Minio = Depends(get_minio),
    db: AsyncSession = Depends(get_db),
):
    """Create an enroll job that uploads and finalizes within the same request."""
    del model, auto_start

    if not audio.filename or not validate_extension(audio.filename):
        raise HTTPException(400, "Unsupported audio format")

    resolved_speaker_id, resolved_speaker_name = await _resolve_speaker(
        db=db,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
    )

    job_id = uuid.uuid4().hex
    object_key = _build_audio_object_key(resolved_speaker_id, audio.filename, job_id[:8])
    redis_client = get_redis_client()
    created = create_enroll_job(redis_client, job_id)

    payload = {
        "job_id": job_id,
        "object_key": object_key,
        "original_filename": audio.filename,
        "speaker_id": resolved_speaker_id,
        "speaker_name": resolved_speaker_name,
    }
    store_enroll_job_payload(redis_client, job_id, payload)

    tmp_dir = tempfile.mkdtemp(prefix=f"enroll-job-{job_id[:8]}-")
    try:
        ext = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
        local_path = os.path.join(tmp_dir, f"audio{ext}")
        with open(local_path, "wb") as f:
            f.write(await audio.read())

        mark_enroll_job_running(redis_client, job_id, stage="upload", progress=5)

        try:
            await asyncio.to_thread(
                upload_file,
                minio_client,
                object_key,
                local_path,
                content_type=audio.content_type or "application/octet-stream",
            )
        except Exception as exc:
            logger.exception("Failed to upload enroll audio for job %s", job_id)
            fail_enroll_job(redis_client, job_id, error="Failed to upload audio")
            raise HTTPException(500, "Failed to upload audio") from exc

        created = await _finalize_enroll_job(redis_client, job_id, payload, db)

        return {
            "job_id": job_id,
            "speaker_id": resolved_speaker_id,
            "status": created["status"],
            "stage": created["stage"],
            "progress": created["progress"],
            "eta_seconds": created["eta_seconds"],
            "error": created.get("error"),
            "result": created.get("result"),
            "poll_url": f"/api/v1/enroll/jobs/{job_id}",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to prepare enroll job %s", job_id)
        fail_enroll_job(redis_client, job_id, error=str(exc))
        raise HTTPException(500, "Failed to create enroll job") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/enroll/jobs/{job_id}")
async def get_enroll_job_endpoint(job_id: str):
    """Fetch asynchronous enroll job status, progress, and result."""
    redis_client = get_redis_client()
    job = get_enroll_job(redis_client, job_id)
    if job is None:
        raise HTTPException(404, "Enroll job not found")
    return job


@router.post("/enroll/jobs/{job_id}/start", status_code=202)
async def start_enroll_job_endpoint(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Persist a staged raw upload and queue background processing."""
    redis_client = get_redis_client()
    job = get_enroll_job(redis_client, job_id)
    if job is None:
        raise HTTPException(404, "Enroll job not found")

    stage = str(job.get("stage") or "")
    status = str(job.get("status") or "")
    if status in {"running", "succeeded"} or stage == "queued":
        raise HTTPException(409, "Enroll job already started")
    if status == "failed":
        raise HTTPException(409, "Failed enroll job cannot be restarted")

    payload = load_enroll_job_payload(redis_client, job_id)
    if payload is None:
        raise HTTPException(404, "Enroll job payload not found")

    return await _finalize_enroll_job(redis_client, job_id, payload, db)
