"""Dramatiq worker tasks for async-heavy operations."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.config import settings
from app.core.calibration import CalibratorRegistry
from app.core.denoise import Denoiser
from app.core.embedder import EmbedderRegistry
from app.core.preprocessing import AudioPreprocessor
from app.core.separator import VocalSeparator
from app.core.telemetry import setup_telemetry
from app.core.vad import VoiceActivityDetector
from app.core.verify_jobs import (
    complete_verify_job,
    fail_verify_job,
    get_redis_client,
    mark_verify_job_running,
    update_verify_job_progress,
)
from app.core.verify_service import load_speaker_reference_embedding, run_verify_pipeline
from app.db.session import async_session_factory
from app.storage.minio_client import delete_objects_by_prefix, download_file, init_minio

logger = logging.getLogger(__name__)

# Initialise OTEL for the worker process (service name overridden via
# OTEL_SERVICE_NAME=voiceprint-worker in docker-compose).
setup_telemetry(settings.otel_service_name, settings.otel_exporter_otlp_endpoint)

redis_broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(redis_broker)


@dataclass
class _VerifyRuntime:
    registry: EmbedderRegistry
    calibrators: CalibratorRegistry
    preprocessor: AudioPreprocessor


_verify_runtime: _VerifyRuntime | None = None


def _format_job_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail
    return str(exc)


def _get_verify_runtime() -> _VerifyRuntime:
    global _verify_runtime
    if _verify_runtime is not None:
        return _verify_runtime

    registry = EmbedderRegistry()
    calibrators = CalibratorRegistry()
    for model_cfg in settings.get_enabled_models():
        registry.register(model_cfg)
        calibrators.register(model_cfg)

    preprocessor = AudioPreprocessor(
        vad=VoiceActivityDetector(),
        separator=VocalSeparator(cfg=settings),
        denoiser=Denoiser(),
        cfg=settings,
    )

    _verify_runtime = _VerifyRuntime(
        registry=registry,
        calibrators=calibrators,
        preprocessor=preprocessor,
    )
    return _verify_runtime


@dramatiq.actor(max_retries=0)
def process_verify_job(payload: dict):
    """Run a queued verify request and persist progress/result to Redis."""
    job_id = str(payload.get("job_id", "")).strip()
    if not job_id:
        logger.error("Missing job_id in verify payload")
        return

    redis_client = get_redis_client()
    mark_verify_job_running(redis_client, job_id, stage="download", progress=5)

    storage_prefix = str(payload.get("storage_prefix", "")).strip()
    audio_a_key = str(payload.get("audio_a_key", "")).strip()
    audio_b_key = payload.get("audio_b_key")
    model_id = str(payload.get("model") or settings.default_model)
    speaker_id_raw = payload.get("speaker_id")
    speaker_id = int(speaker_id_raw) if speaker_id_raw is not None else None

    use_separation = bool(payload.get("separate_vocals", settings.preprocess_separate_vocals))
    use_denoise = bool(payload.get("denoise", settings.preprocess_denoise))
    include_timings = bool(payload.get("include_timings", False))
    enable_fast_return = bool(payload.get("enable_fast_return", False))
    fast_return_margin = float(payload.get("fast_return_margin", 0.18))

    tmp_dir = tempfile.mkdtemp(prefix=f"verify-job-{job_id[:8]}-")
    try:
        if not audio_a_key:
            raise ValueError("audio_a_key is required")

        minio_client = init_minio()

        ext_a = os.path.splitext(audio_a_key)[1] or ".wav"
        path_a = os.path.join(tmp_dir, f"audio_a{ext_a}")
        download_file(minio_client, audio_a_key, path_a)

        path_b = None
        if audio_b_key:
            ext_b = os.path.splitext(str(audio_b_key))[1] or ".wav"
            path_b = os.path.join(tmp_dir, f"audio_b{ext_b}")
            download_file(minio_client, str(audio_b_key), path_b)

        runtime = _get_verify_runtime()
        if model_id not in runtime.registry.available_ids:
            raise ValueError(f"Unknown or disabled model: {model_id}")

        embedder = runtime.registry.get(model_id)
        calibrator = runtime.calibrators.get(model_id)
        model_cfg = settings.get_model(model_id)
        threshold = model_cfg.verify_threshold if model_cfg else settings.verify_threshold

        def _progress_callback(stage: str, progress: int) -> None:
            update_verify_job_progress(
                redis_client,
                job_id,
                stage=stage,
                progress=progress,
            )

        async def _load_speaker_embedding(request_speaker_id: int):
            async with async_session_factory() as db:
                return await load_speaker_reference_embedding(
                    db,
                    request_speaker_id,
                    model_id,
                )

        result = asyncio.run(
            run_verify_pipeline(
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
                preprocessor=runtime.preprocessor,
                load_speaker_embedding=_load_speaker_embedding if speaker_id is not None else None,
                progress_hook=_progress_callback,
            )
        )

        complete_verify_job(redis_client, job_id, result=result)
    except Exception as exc:
        logger.exception("Verify job %s failed", job_id)
        fail_verify_job(redis_client, job_id, error=_format_job_error(exc))
        return
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if storage_prefix:
            try:
                minio_client = init_minio()
                delete_objects_by_prefix(minio_client, f"{storage_prefix}/")
            except Exception:
                logger.exception("Failed to clean up objects for verify job %s", job_id)


@dramatiq.actor(max_retries=3, min_backoff=10_000)
def separate_vocals(audio_storage_key: str, speaker_id: int | None = None):
    """Run Demucs vocal separation on an uploaded audio file.

    This is a placeholder for the future vocal-separation pipeline.
    Intended flow:
      1. Download audio from MinIO by storage_key
      2. Run Demucs to extract vocal track
      3. Normalise → VAD → embed the vocal track
      4. Store the separated vocal in MinIO
      5. If speaker_id provided, store embedding in DB
    """
    # TODO: implement Demucs pipeline
    raise NotImplementedError("Vocal separation not yet implemented")
