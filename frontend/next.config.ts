import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  // Prevent webpack from bundling Node.js-native OTEL packages.
  // They are loaded at runtime via the instrumentation hook instead.
  serverExternalPackages: [
    "@opentelemetry/sdk-node",
    "@opentelemetry/sdk-trace-node",
    "@opentelemetry/sdk-trace-base",
    "@opentelemetry/sdk-metrics",
    "@opentelemetry/instrumentation-http",
    "@opentelemetry/exporter-trace-otlp-http",
    "@opentelemetry/resources",
  ],
};

export default withNextIntl(nextConfig);
