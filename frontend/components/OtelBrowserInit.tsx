"use client";

/**
 * Browser-side OpenTelemetry initialisation.
 *
 * Mounted once at the root layout.  Initialises a WebTracerProvider that:
 *   • Traces all outgoing fetch() calls (FetchInstrumentation)
 *   • Records page-load performance (DocumentLoadInstrumentation)
 *   • Captures uncaught JS errors and unhandled promise rejections
 *
 * Spans are batched and sent to /api/otel/traces (same-origin proxy → SigNoz).
 * The component renders nothing — it is side-effects only.
 */

import { useEffect } from "react";
import type { WebTracerProvider } from "@opentelemetry/sdk-trace-web";

// Module-level singleton — survives React Strict Mode double-effect
let _provider: WebTracerProvider | null = null;

export function OtelBrowserInit() {
  useEffect(() => {
    // SSR guard (should not be needed for "use client", but be safe)
    if (typeof window === "undefined") return;

    async function init() {
      // Lazy-import OTEL browser packages — keeps the initial bundle clean
      const { WebTracerProvider } = await import(
        "@opentelemetry/sdk-trace-web"
      );
      const { BatchSpanProcessor } = await import(
        "@opentelemetry/sdk-trace-base"
      );
      const { OTLPTraceExporter } = await import(
        "@opentelemetry/exporter-trace-otlp-http"
      );
      const { registerInstrumentations } = await import(
        "@opentelemetry/instrumentation"
      );
      const { FetchInstrumentation } = await import(
        "@opentelemetry/instrumentation-fetch"
      );
      const { DocumentLoadInstrumentation } = await import(
        "@opentelemetry/instrumentation-document-load"
      );
      const { Resource } = await import("@opentelemetry/resources");

      if (_provider) return; // already initialised (Strict Mode second call)

      _provider = new WebTracerProvider({
        resource: new Resource({ "service.name": "voiceprint-browser" }),
      });

      _provider.addSpanProcessor(
        new BatchSpanProcessor(
          new OTLPTraceExporter({ url: "/api/otel/traces" })
        )
      );

      // Use default StackContextManager (no zone.js dependency)
      _provider.register();

      registerInstrumentations({
        tracerProvider: _provider,
        instrumentations: [
          // Trace all browser fetch() calls (includes API route calls)
          new FetchInstrumentation({
            // Propagate W3C traceparent to same-origin requests so the
            // browser trace links to the Next.js server-side trace.
            propagateTraceHeaderCorsUrls: [new RegExp(window.location.origin)],
          }),
          // Record navigation & resource timing as a span on page load
          new DocumentLoadInstrumentation(),
        ],
      });
    }

    void init();

    // ── Global error capture ────────────────────────────────────────────
    // Error handlers reference the provider lazily so they work even
    // if init() hasn't resolved yet (provider will be set synchronously
    // before the first microtask tick after import resolution).

    const onError = (event: ErrorEvent) => {
      if (!_provider) return;
      const tracer = _provider.getTracer("browser-errors");
      const span = tracer.startSpan("browser.uncaught_error");
      span.recordException({
        name: event.error?.name ?? "Error",
        message: event.message,
        stack: event.error?.stack,
      });
      span.setStatus({ code: 2 /* SpanStatusCode.ERROR */, message: event.message });
      span.setAttribute("error.type", "uncaught");
      span.end();
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      if (!_provider) return;
      const tracer = _provider.getTracer("browser-errors");
      const span = tracer.startSpan("browser.unhandled_rejection");
      const err =
        event.reason instanceof Error
          ? event.reason
          : new Error(String(event.reason));
      span.recordException(err);
      span.setStatus({ code: 2, message: err.message });
      span.setAttribute("error.type", "unhandledrejection");
      span.end();
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);

    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, []);

  return null;
}
