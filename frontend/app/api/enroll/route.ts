import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export const maxDuration = 600; // 10 minutes — large audio files take time

export async function POST(request: NextRequest) {
  const formData = await request.formData();

  const res = await fetch(aiUrl("/api/v1/enroll"), {
    method: "POST",
    headers: buildAiProxyHeaders(request),
    body: formData,
  });

  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));

  return NextResponse.json(data, { status: res.status });
}
