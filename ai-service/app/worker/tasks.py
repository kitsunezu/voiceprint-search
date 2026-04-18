"""Dramatiq worker tasks for async-heavy operations."""

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.config import settings
from app.core.telemetry import setup_telemetry

# Initialise OTEL for the worker process (service name overridden via
# OTEL_SERVICE_NAME=voiceprint-worker in docker-compose).
setup_telemetry(settings.otel_service_name, settings.otel_exporter_otlp_endpoint)

redis_broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(redis_broker)


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
