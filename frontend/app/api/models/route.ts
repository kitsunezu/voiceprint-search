import { NextResponse } from "next/server";

const AI_BASE = process.env.AI_SERVICE_URL ?? "http://localhost:8000";

export async function GET() {
  const res = await fetch(`${AI_BASE}/api/v1/models`, { cache: "no-store" });
  const data = await res.json().catch(() => ({ models: [], default_model: "" }));
  return NextResponse.json(data, { status: res.status });
}
