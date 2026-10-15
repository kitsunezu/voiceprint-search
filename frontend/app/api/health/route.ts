import { NextResponse } from "next/server";

import { aiUrl } from "@/app/api/_lib/ai-proxy";

export async function GET() {
  try {
    const response = await fetch(aiUrl("/api/v1/health"), {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const health = await response.json();
    const ok = response.ok && health.status === "ok"
      && health.db_connected === true && health.model_loaded === true;
    return NextResponse.json({
      ok,
      revision: typeof health.revision === "string" ? health.revision : null,
    }, { status: ok ? 200 : 503, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ ok: false }, {
      status: 503, headers: { "Cache-Control": "no-store" },
    });
  }
}
