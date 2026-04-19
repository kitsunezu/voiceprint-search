"""1:1 speaker verification endpoints."""

import os
import shutil
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_calibrator_registry,
    get_db,
    get_embedder_registry,
    get_minio,
    get_preprocessor,
)
from app.config import settings
from app.core.audio import validate_extension
from app.core.calibration import CalibratorRegistry
from app.core.embedder import EmbedderRegistry
from app.core.preprocessing import AudioPreprocessor
from app.core.verify_jobs import (
    create_verify_job,
    fail_verify_job,
    get_redis_client,
    get_verify_job,
)
from app.core.verify_service import load_speaker_reference_embedding, run_verify_pipeline
from app.storage.minio_client import upload_file

router = APIRouter()


def _resolve_model_and_threshold(
    registry: EmbedderRegistry,
    model: str,
) -> tuple[str, float]:
    model_id = model.strip() or settings.default_model
    if model_id not in registry.available_ids:
        raise HTTPException(400, f"Unknown or disabled model: {model_id}")

    model_cfg = settings.get_model(model_id)
    threshold = model_cfg.verify_threshold if model_cfg else settings.verify_threshold
    return model_id, threshold


def _validate_upload(file: UploadFile | None) -> None:
    if file and (not file.filename or not validate_extension(file.filename)):
        raise HTTPException(400, "Unsupported audio format")


@router.post("/verify")
async def verify(
    audio_a: UploadFile = File(...),
    audio_b: UploadFile | None = File(None),
    speaker_id: int | None = Form(None),
    model: str = Form(""),
    separate_vocals: bool | None = Form(None),
    denoise: bool | None = Form(None),
    include_timings: bool = Form(False),
    enable_fast_return: bool = Form(False),
    fast_return_margin: float = Form(0.18),
    db: AsyncSession = Depends(get_db),
    registry: EmbedderRegistry = Depends(get_embedder_registry),
    calibrators: CalibratorRegistry = Depends(get_calibrator_registry),
    preprocessor: AudioPreprocessor = Depends(get_preprocessor),
):
    """Compare two audio clips, or one clip against an enrolled speaker."""
    if audio_b is None and speaker_id is None:
        raise HTTPException(400, "Provide either audio_b or speaker_id")

    _validate_upload(audio_a)
    _validate_upload(audio_b)

    model_id, threshold = _resolve_model_and_threshold(registry, model)
    embedder = registry.get(model_id)
    calibrator = calibrators.get(model_id)

    use_separation = settings.preprocess_separate_vocals if separate_vocals is None else separate_vocals
    use_denoise = settings.preprocess_denoise if denoise is None else denoise

    tmp_dir = tempfile.mkdtemp()
    try:
        ext_a = os.path.splitext(audio_a.filename or "audio.wav")[1] or ".wav"
        path_a = os.path.join(tmp_dir, f"a_{uuid.uuid4().hex[:8]}{ext_a}")
        with open(path_a, "wb") as f:
            f.write(await audio_a.read())

        path_b = None
        if audio_b is not None:
            ext_b = os.path.splitext(audio_b.filename or "audio.wav")[1] or ".wav"
            path_b = os.path.join(tmp_dir, f"b_{uuid.uuid4().hex[:8]}{ext_b}")
            with open(path_b, "wb") as f:
                f.write(await audio_b.read())

        async def _load_speaker_embedding(request_speaker_id: int):
            return await load_speaker_reference_embedding(db, request_speaker_id, model_id)

        return await run_verify_pipeline(
            path_a=path_a,
            path_b=path_b,
            speaker_id=speaker_id,
            model_id=model_id,
            threshold=threshold,
            separate_vocals=use_separation,
            denoise=use_denoise,
            include_timings=include_timings,
            enable_fast_return=enable_fast_return,
            fast_return_margin=fast_return_margin,
            embedder=embedder,
            calibrator=calibrator,
            preprocessor=preprocessor,
            load_speaker_embedding=_load_speaker_embedding if speaker_id is not None else None,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/verify/jobs", status_code=202)
async def create_verify_job_endpoint(
    audio_a: UploadFile = File(...),
    audio_b: UploadFile | None = File(None),
    speaker_id: int | None = Form(None),
    model: str = Form(""),
    separate_vocals: bool | None = Form(None),
    denoise: bool | None = Form(None),
    include_timings: bool = Form(False),
    enable_fast_return: bool = Form(False),
    fast_return_margin: float = Form(0.18),
    registry: EmbedderRegistry = Depends(get_embedder_registry),
    minio_client: Minio = Depends(get_minio),
):
    """Create an asynchronous verify job and return a job ID."""
    if audio_b is None and speaker_id is None:
        raise HTTPException(400, "Provide either audio_b or speaker_id")

    _validate_upload(audio_a)
    _validate_upload(audio_b)

    model_id, _ = _resolve_model_and_threshold(registry, model)
    use_separation = settings.preprocess_separate_vocals if separate_vocals is None else separate_vocals
    use_denoise = settings.preprocess_denoise if denoise is None else denoise

    fast_return_margin = max(0.0, min(float(fast_return_margin), 1.0))

    job_id = uuid.uuid4().hex
    storage_prefix = f"verify-jobs/{job_id}"

    tmp_dir = tempfile.mkdtemp()
    try:
        ext_a = os.path.splitext(audio_a.filename or "audio.wav")[1] or ".wav"
        local_a = os.path.join(tmp_dir, f"audio_a{ext_a}")
        with open(local_a, "wb") as f:
            f.write(await audio_a.read())

        audio_a_key = f"{storage_prefix}/audio_a{ext_a}"
        upload_file(
            minio_client,
            audio_a_key,
            local_a,
            content_type=audio_a.content_type or "application/octet-stream",
        )

        audio_b_key = None
        if audio_b is not None:
            ext_b = os.path.splitext(audio_b.filename or "audio.wav")[1] or ".wav"
            local_b = os.path.join(tmp_dir, f"audio_b{ext_b}")
            with open(local_b, "wb") as f:
                f.write(await audio_b.read())

            audio_b_key = f"{storage_prefix}/audio_b{ext_b}"
            upload_file(
                minio_client,
                audio_b_key,
                local_b,
                content_type=audio_b.content_type or "application/octet-stream",
            )

        redis_client = get_redis_client()
        created = create_verify_job(redis_client, job_id)

        payload = {
            "job_id": job_id,
            "storage_prefix": storage_prefix,
            "audio_a_key": audio_a_key,
            "audio_b_key": audio_b_key,
            "speaker_id": speaker_id,
            "model": model_id,
            "separate_vocals": bool(use_separation),
            "denoise": bool(use_denoise),
            "include_timings": bool(include_timings),
            "enable_fast_return": bool(enable_fast_return),
            "fast_return_margin": fast_return_margin,
        }

        try:
            from app.worker.tasks import process_verify_job

            process_verify_job.send(payload)
        except Exception as exc:
            fail_verify_job(redis_client, job_id, error=f"Failed to enqueue verify job: {exc}")
            raise HTTPException(500, "Failed to enqueue verify job")

        return {
            "job_id": job_id,
            "status": created["status"],
            "stage": created["stage"],
            "progress": created["progress"],
            "eta_seconds": created["eta_seconds"],
            "poll_url": f"/api/v1/verify/jobs/{job_id}",
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/verify/jobs/{job_id}")
async def get_verify_job_endpoint(job_id: str):
    """Fetch asynchronous verify job status, progress, ETA, and result."""
    redis_client = get_redis_client()
    job = get_verify_job(redis_client, job_id)
    if job is None:
        raise HTTPException(404, "Verify job not found")
    return job
