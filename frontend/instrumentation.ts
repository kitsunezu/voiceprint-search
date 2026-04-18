/**
 * Next.js instrumentation hook — runs once in the Node.js server process.
 * Initialises OpenTelemetry traces and sends them to SigNoz via OTLP HTTP.
 *
 * Activated by setting OTEL_EXPORTER_OTLP_ENDPOINT in the environment.
 * When the variable is absent the function exits immediately (safe for dev).
 *
 * @see https://nextjs.org/docs/app/building-your-application/optimizing/open-telemetry
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "";
  if (!endpoint) return;

  const { NodeSDK } = await import("@opentelemetry/sdk-node");
  const { OTLPTraceExporter } = await import(
    "@opentelemetry/exporter-trace-otlp-http"
  );
  const { HttpInstrumentation } = await import(
    "@opentelemetry/instrumentation-http"
  );
  const { Resource } = await import("@opentelemetry/resources");

  const sdk = new NodeSDK({
    resource: new Resource({
      "service.name":
        process.env.OTEL_SERVICE_NAME ?? "voiceprint-frontend",
    }),
    traceExporter: new OTLPTraceExporter({
      url: `${endpoint.replace(/\/$/, "")}/v1/traces`,
    }),
    instrumentations: [
      new HttpInstrumentation({
        // Record request/response headers useful for debugging
        headersToSpanAttributes: {
          server: {
            requestHeaders: ["x-forwarded-for", "user-agent"],
            responseHeaders: ["content-type"],
          },
        },
      }),
    ],
  });

  sdk.start();
}
