import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export async function GET(request: NextRequest) {
  const res = await fetch(aiUrl("/api/v1/speakers"), {
    cache: "no-store",
    headers: buildAiProxyHeaders(request),
  });
  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));
  return NextResponse.json(data, { status: res.status });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const res = await fetch(aiUrl("/api/v1/speakers"), {
    method: "POST",
    headers: buildAiProxyHeaders(request, {
      "content-type": "application/json",
    }),
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));
  return NextResponse.json(data, { status: res.status });
}
