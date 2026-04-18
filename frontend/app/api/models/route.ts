import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export async function GET(request: NextRequest) {
  const res = await fetch(aiUrl("/api/v1/models"), {
    cache: "no-store",
    headers: buildAiProxyHeaders(request),
  });
  const data = await res.json().catch(() => ({ models: [], default_model: "" }));
  return NextResponse.json(data, { status: res.status });
}
