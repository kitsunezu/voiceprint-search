"""OpenTelemetry initialisation — traces, metrics and logs via OTLP HTTP.

Call ``setup_telemetry(service_name, endpoint)`` once at process startup,
before the FastAPI app is created.  When *endpoint* is empty the function
is a no-op, so local development works without any SigNoz instance.
"""

from __future__ import annotations

import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Logs SDK — path changed between opentelemetry-sdk 1.20 and 1.22.
# Try the stable (non-underscore) path first, fall back to the experimental one.
try:
    from opentelemetry.sdk.logs import LoggerProvider, LoggingHandler  # type: ignore[attr-defined]
    from opentelemetry.sdk.logs.export import BatchLogRecordProcessor  # type: ignore[attr-defined]
    from opentelemetry.exporter.otlp.proto.http.log_exporter import OTLPLogExporter  # type: ignore[attr-defined]
    from opentelemetry._logs import set_logger_provider  # type: ignore[attr-defined]
    _LOGS_AVAILABLE = True
except ImportError:
    try:
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler  # type: ignore[no-redef]
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor  # type: ignore[no-redef]
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter  # type: ignore[no-redef]
        from opentelemetry._logs import set_logger_provider  # type: ignore[no-redef]
        _LOGS_AVAILABLE = True
    except ImportError:
        _LOGS_AVAILABLE = False

from opentelemetry.instrumentation.logging import LoggingInstrumentor

_logger = logging.getLogger(__name__)
_ROOT_LOGGER_CONFIG_ATTR = "_voiceprint_otel_config"
_OTEL_HANDLER_ATTR = "_voiceprint_otel_handler"


def setup_telemetry(service_name: str, endpoint: str) -> None:
    """Initialise OTEL traces, metrics and logs, exporting via OTLP HTTP.

    Does nothing when *endpoint* is empty — safe to call unconditionally.
    """
    if not endpoint:
        return

    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)

    base = endpoint.rstrip("/")
    existing_config = getattr(root_logger, _ROOT_LOGGER_CONFIG_ATTR, None)
    if existing_config:
        if existing_config == (service_name, base):
            return

        _logger.warning(
            "OpenTelemetry already initialised for %s (service=%s); skipping reinitialisation for %s",
            existing_config[1],
            existing_config[0],
            service_name,
        )
        return

    resource = Resource.create({"service.name": service_name})

    # ── Traces ────────────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    # ── Metrics (exported every 60 s) ─────────────────────────────────────
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{base}/v1/metrics"),
                export_interval_millis=60_000,
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    # ── Logs ──────────────────────────────────────────────────────────────
    if _LOGS_AVAILABLE:
        try:
            log_provider = LoggerProvider(resource=resource)  # type: ignore[possibly-undefined]
            log_provider.add_log_record_processor(
                BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs"))  # type: ignore[possibly-undefined]
            )
            set_logger_provider(log_provider)  # type: ignore[possibly-undefined]

            # Bridge Python root logging → OTEL (INFO and above sent to SigNoz)
            if not any(
                getattr(handler, _OTEL_HANDLER_ATTR, False)
                for handler in root_logger.handlers
            ):
                otel_handler = LoggingHandler(  # type: ignore[possibly-undefined]
                    level=logging.INFO, logger_provider=log_provider
                )
                setattr(otel_handler, _OTEL_HANDLER_ATTR, True)
                root_logger.addHandler(otel_handler)
        except Exception as exc:
            _logger.warning("OTEL log setup failed, skipping: %s", exc)

    # Inject trace_id / span_id into every Python log record
    try:
        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception as exc:
        _logger.warning("LoggingInstrumentor skipped: %s", exc)

    setattr(root_logger, _ROOT_LOGGER_CONFIG_ATTR, (service_name, base))

    _logger.info(
        "OpenTelemetry initialised → %s (service=%s, logs=%s)",
        base,
        service_name,
        _LOGS_AVAILABLE,
    )
