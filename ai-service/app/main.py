from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.config import settings
from app.core.telemetry import setup_telemetry
from app.core.embedder import EmbedderRegistry
from app.core.vad import VoiceActivityDetector
from app.core.separator import VocalSeparator
from app.core.denoise import Denoiser
from app.core.preprocessing import AudioPreprocessor
from app.core.calibration import CalibratorRegistry
from app.db.session import engine, async_session_factory
from app.storage.minio_client import init_minio
from app.api.router import api_router

logger = logging.getLogger(__name__)

# Initialise OTEL before app creation so providers are set for all modules.
# When OTEL_EXPORTER_OTLP_ENDPOINT is not configured this is a no-op.
setup_telemetry(settings.otel_service_name, settings.otel_exporter_otlp_endpoint)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    # Build embedder registry for all enabled models
    registry = EmbedderRegistry()
    enabled = settings.get_enabled_models()
    for mcfg in enabled:
        registry.register(mcfg)
        logger.info("Registered model %s (%s)", mcfg.id, mcfg.backend)

    # Eagerly preload the default model so first request is fast
    try:
        registry.preload(settings.default_model)
    except Exception:
        logger.warning("Could not preload default model %s", settings.default_model)

    app.state.embedder_registry = registry
    # Backward compat: keep a single embedder reference for any code still using it
    try:
        app.state.embedder = registry.get(settings.default_model)
    except Exception:
        app.state.embedder = None

    app.state.vad = VoiceActivityDetector()
    app.state.separator = VocalSeparator(cfg=settings)
    logger.info(
        "Separator profile %s (%s:%s)",
        app.state.separator.profile.id,
        app.state.separator.profile.backend,
        app.state.separator.profile.model,
    )
    app.state.denoiser = Denoiser()
    app.state.preprocessor = AudioPreprocessor(
        vad=app.state.vad,
        separator=app.state.separator,
        denoiser=app.state.denoiser,
        cfg=settings,
    )

    # Build per-model calibrators
    calibrators = CalibratorRegistry()
    for mcfg in enabled:
        calibrators.register(mcfg)
    app.state.calibrator_registry = calibrators
    # Backward compat
    app.state.calibrator = calibrators.get(settings.default_model)

    app.state.db = async_session_factory
    app.state.minio = init_minio()

    yield

    # ── Shutdown ──
    await engine.dispose()


app = FastAPI(
    title="Voiceprint Search AI Service",
    version="0.1.0",
    lifespan=lifespan,
)

# ── OpenTelemetry FastAPI auto-instrumentation ────────────────────────────

def _otel_server_request_hook(span, scope: dict) -> None:
    """Attach the real client IP (honoring X-Forwarded-For) to each span."""
    if not span or not span.is_recording():
        return
    raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    headers = {k.lower(): v.decode("latin-1") for k, v in raw_headers}
    xff = headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else ""
    if not ip:
        client = scope.get("client")
        if client:
            ip = client[0]
    if ip:
        span.set_attribute("client.ip", ip)


if settings.otel_exporter_otlp_endpoint:
    FastAPIInstrumentor().instrument_app(
        app, server_request_hook=_otel_server_request_hook
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
