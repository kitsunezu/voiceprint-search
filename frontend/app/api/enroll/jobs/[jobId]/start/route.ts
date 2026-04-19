import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;

  const res = await fetch(aiUrl(`/api/v1/enroll/jobs/${jobId}/start`), {
    method: "POST",
    headers: buildAiProxyHeaders(request),
  });

  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));

  return NextResponse.json(data, { status: res.status });
}
