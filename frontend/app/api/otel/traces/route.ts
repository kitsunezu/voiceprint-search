/**
 * OTLP traces proxy — forwards browser-side span batches to SigNoz.
 *
 * Browsers cannot call the SigNoz OTLP endpoint directly (CORS + private
 * network).  The browser SDK sends POST /api/otel/traces (same-origin), and
 * this route relays it to the internal OTEL_EXPORTER_OTLP_ENDPOINT.
 */
import { NextRequest, NextResponse } from "next/server";

const OTLP_BASE = (process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "").replace(
  /\/$/,
  ""
);

export async function POST(request: NextRequest) {
  if (!OTLP_BASE) {
    return NextResponse.json(
      { error: "OTLP endpoint not configured" },
      { status: 503 }
    );
  }

  const body = await request.arrayBuffer();
  const contentType =
    request.headers.get("content-type") ?? "application/json";

  try {
    const res = await fetch(`${OTLP_BASE}/v1/traces`, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body,
    });
    // Return minimal response — the browser SDK only checks for 2xx
    return new NextResponse(null, { status: res.ok ? 200 : res.status });
  } catch {
    return NextResponse.json(
      { error: "Failed to forward traces to OTLP endpoint" },
      { status: 502 }
    );
  }
}
