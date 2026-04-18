import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 600; // 10 minutes — large audio files take time

const AI_BASE = process.env.AI_SERVICE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const formData = await request.formData();

  const res = await fetch(`${AI_BASE}/api/v1/verify`, {
    method: "POST",
    body: formData,
  });

  const data = await res.json().catch(() => ({ detail: "AI service unavailable" }));

  return NextResponse.json(data, { status: res.status });
}
