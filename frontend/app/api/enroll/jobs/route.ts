import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export const maxDuration = 600; // Large uploads may take time before the job is queued.

export async function POST(request: NextRequest) {
  const formData = await request.formData();

  const res = await fetch(aiUrl("/api/v1/enroll/jobs"), {
    method: "POST",
    headers: buildAiProxyHeaders(request),
    body: formData,
  });

  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));

  return NextResponse.json(data, { status: res.status });
}
