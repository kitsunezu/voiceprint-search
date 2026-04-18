import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  // Forward Range header so the browser can seek
  const upstreamHeaders = buildAiProxyHeaders(req);
  const range = req.headers.get("range");
  if (range) upstreamHeaders.set("Range", range);

  const res = await fetch(
    aiUrl(`/api/v1/speakers/${encodeURIComponent(id)}/audio`),
    { cache: "no-store", headers: upstreamHeaders },
  );

  if (!res.ok && res.status !== 206) {
    return NextResponse.json({ detail: "Audio not available" }, { status: res.status });
  }

  const buffer = await res.arrayBuffer();

  const responseHeaders: Record<string, string> = {
    "Content-Type": res.headers.get("content-type") ?? "audio/wav",
    "Accept-Ranges": "bytes",
    "Cache-Control": "private, max-age=60",
  };
  const contentRange = res.headers.get("content-range");
  if (contentRange) responseHeaders["Content-Range"] = contentRange;
  const contentLength = res.headers.get("content-length");
  if (contentLength) responseHeaders["Content-Length"] = contentLength;

  return new NextResponse(buffer, {
    status: res.status,
    headers: responseHeaders,
  });
}
