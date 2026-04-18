"""Speaker enroll endpoint — register a new speaker with an audio sample."""

import os
import re
import shutil
import tempfile
import uuid

import numpy as np
import scipy.io.wavfile as _wavfile
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_embedder_registry, get_minio, get_preprocessor
from app.config import settings
from app.core.audio import validate_extension
from app.core.embedder import EmbedderRegistry, embed_segments
from app.core.preprocessing import AudioPreprocessor, PreprocessError
from app.db import repository as repo
from app.storage.minio_client import upload_file
from minio import Minio

router = APIRouter()


@router.post("/enroll", status_code=201)
async def enroll_speaker(
    audio: UploadFile = File(...),
    speaker_name: str = Form(...),
    speaker_id: int | None = Form(None),
    model: str = Form(""),
    # separate_vocals kept for backward compat but ignored — always True now
    separate_vocals: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    registry: EmbedderRegistry = Depends(get_embedder_registry),
    minio_client: Minio = Depends(get_minio),
    preprocessor: AudioPreprocessor = Depends(get_preprocessor),
):
    if not audio.filename or not validate_extension(audio.filename):
        raise HTTPException(400, "Unsupported audio format")

    if audio.size and audio.size > settings.max_upload_bytes:
        raise HTTPException(413, "File too large")

    model_id = model.strip() or settings.default_model
    if model_id not in registry.available_ids:
        raise HTTPException(400, f"Unknown or disabled model: {model_id}")

    embedder = registry.get(model_id)

    tmp_dir = tempfile.mkdtemp()
    cleanup_dirs: list[str] = []
    try:
        # Save upload to temp file
        ext = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
        raw_path = os.path.join(tmp_dir, f"raw_{uuid.uuid4().hex[:8]}{ext}")
        with open(raw_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        # ── Mandatory preprocessing pipeline ──
        try:
            result, pp_dirs = preprocessor.process(raw_path)
        except PreprocessError as exc:
            raise HTTPException(422, str(exc))
        cleanup_dirs.extend(pp_dirs)

        # Compute embedding (multi-segment averaging for long audio)
        embedding = embed_segments(embedder, result.segments)

        # Save processed vocal audio (VAD-extracted, vocals-separated) for playback.
        # This gives a clean, short voice sample instead of the full original song.
        SAMPLE_RATE = 16_000
        vocal_wav_path = os.path.join(tmp_dir, f"vocal_{uuid.uuid4().hex[:8]}.wav")
        pcm = (np.clip(result.analysis_waveform, -1.0, 1.0) * 32767).astype(np.int16)
        _wavfile.write(vocal_wav_path, SAMPLE_RATE, pcm)
        duration = len(result.analysis_waveform) / SAMPLE_RATE

        # Get or create speaker
        if speaker_id:
            speaker = await repo.get_speaker(db, speaker_id)
            if not speaker:
                raise HTTPException(404, f"Speaker ID {speaker_id} not found")
        else:
            speaker = await repo.create_speaker(db, name=speaker_name)
            await db.flush()

        # Upload to MinIO
        stem = os.path.splitext(audio.filename or "audio")[0]
        stem = re.sub(r'[/\\\u29f8\u2044\u2215\x00-\x1f\x7f]+', '-', stem).strip(' -')
        ext_bytes = len(ext.encode())
        max_stem_bytes = 250 - ext_bytes
        stem_encoded = stem.encode('utf-8')
        if len(stem_encoded) > max_stem_bytes:
            stem_encoded = stem_encoded[:max_stem_bytes]
            stem = stem_encoded.decode('utf-8', errors='ignore').rstrip()
        safe_name = f"{stem or uuid.uuid4().hex}_vocal.wav"
        object_key = f"speakers/{speaker.id}/{safe_name}"
        upload_file(minio_client, object_key, vocal_wav_path)

        # Persist to database
        asset = await repo.create_audio_asset(
            db,
            speaker_id=speaker.id,
            original_filename=audio.filename,
            storage_key=object_key,
            duration_seconds=duration,
            sample_rate=16_000,
        )
        emb = await repo.create_embedding(
            db,
            speaker_id=speaker.id,
            audio_asset_id=asset.id,
            vector=embedding,
            model_version=model_id,
        )

        # Multi-model: embed for every other loaded model too
        for other_id in registry.loaded_ids:
            if other_id == model_id:
                continue
            try:
                other_vec = embed_segments(registry.get(other_id), result.segments)
                await repo.create_embedding(
                    db,
                    speaker_id=speaker.id,
                    audio_asset_id=asset.id,
                    vector=other_vec,
                    model_version=other_id,
                )
            except Exception:
                pass

        await db.commit()

        return {
            "speaker_id": speaker.id,
            "embedding_id": emb.id,
            "message": f"Speaker '{speaker_name}' enrolled successfully",
        }

    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for d in cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)
