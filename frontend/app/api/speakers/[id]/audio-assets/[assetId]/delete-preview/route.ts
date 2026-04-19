import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; assetId: string }> },
) {
  const { id, assetId } = await params;
  const res = await fetch(
    aiUrl(
      `/api/v1/speakers/${encodeURIComponent(id)}/audio-assets/${encodeURIComponent(assetId)}/delete-preview`,
    ),
    {
      cache: "no-store",
      headers: buildAiProxyHeaders(request),
    },
  );
  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));
  return NextResponse.json(data, { status: res.status });
}