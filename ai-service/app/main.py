from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
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

def _extract_first_forwarded_ip(value: str) -> str:
    for segment in value.split(","):
        parts = [part.strip() for part in segment.split(";")]
        for part in parts:
            if not part.lower().startswith("for="):
                continue

            token = part[4:].strip().strip('"')
            if not token or token.lower() == "unknown":
                continue

            if token.startswith("["):
                end = token.find("]")
                return token[1:end] if end >= 0 else token[1:]

            if token.count(":") == 1 and token.replace(":", "").replace(".", "").isdigit():
                return token.split(":", 1)[0]

            return token

    return ""

def _extract_client_network_context(scope: dict) -> tuple[str, str]:
    raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in raw_headers
    }
    internal_forwarded_for = headers.get("x-voiceprint-forwarded-for", "").strip()
    internal_real_ip = headers.get("x-voiceprint-client-ip", "").strip()
    forwarded_for = headers.get("x-forwarded-for", "").strip()
    real_ip = headers.get("x-real-ip", "").strip()
    forwarded = headers.get("forwarded", "").strip()
    forwarded_ip = _extract_first_forwarded_ip(forwarded)

    ip = (
        internal_real_ip
        or real_ip
        or (internal_forwarded_for.split(",")[0].strip() if internal_forwarded_for else "")
        or (forwarded_for.split(",")[0].strip() if forwarded_for else "")
        or forwarded_ip
    )
    if not ip:
        client = scope.get("client")
        if client:
            ip = client[0]

    return ip, internal_forwarded_for or forwarded_for or forwarded_ip


def _should_log_request(path: str) -> bool:
    return path != "/api/v1/health"


@app.middleware("http")
async def _log_request_telemetry(request: Request, call_next):
    client_ip, forwarded_for = _extract_client_network_context(request.scope)

    try:
        response = await call_next(request)
    except Exception:
        if _should_log_request(request.url.path):
            logger.exception(
                "HTTP request failed client_ip=%s method=%s path=%s",
                client_ip or "-",
                request.method,
                request.url.path,
                extra={
                    "client_ip": client_ip,
                    "x_forwarded_for": forwarded_for,
                    "http_method": request.method,
                    "http_path": request.url.path,
                },
            )
        raise

    if _should_log_request(request.url.path):
        logger.info(
            "HTTP request completed client_ip=%s method=%s path=%s status=%s",
            client_ip or "-",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "client_ip": client_ip,
                "x_forwarded_for": forwarded_for,
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status_code": response.status_code,
            },
        )

    return response

def _otel_server_request_hook(span, scope: dict) -> None:
    """Attach the real client IP, honoring proxy forwarding headers."""
    if not span or not span.is_recording():
        return
    ip, _ = _extract_client_network_context(scope)
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
