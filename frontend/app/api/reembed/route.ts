import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

import { NextRequest, NextResponse } from "next/server";

import { aiUrl, buildAiProxyHeaders } from "@/app/api/_lib/ai-proxy";

type ProxyResult = {
  status: number;
  body: string;
};

function proxyLongRunningPost(url: string, headers: Headers): Promise<ProxyResult> {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const requestImpl = target.protocol === "https:" ? httpsRequest : httpRequest;
    const req = requestImpl(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port,
        path: `${target.pathname}${target.search}`,
        method: "POST",
        headers: Object.fromEntries(headers.entries()),
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        res.on("end", () => {
          resolve({
            status: res.statusCode ?? 502,
            body: Buffer.concat(chunks).toString("utf-8"),
          });
        });
      },
    );

    req.setTimeout(0);
    req.on("error", reject);
    req.end();
  });
}

export async function POST(request: NextRequest) {
  const overwrite = request.nextUrl.searchParams.get("overwrite");
  const query = overwrite === null ? "" : `?overwrite=${encodeURIComponent(overwrite)}`;

  try {
    const res = await proxyLongRunningPost(
      aiUrl(`/api/v1/reembed${query}`),
      buildAiProxyHeaders(request),
    );
    const data = JSON.parse(res.body || "{}") as Record<string, unknown>;
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: "AI service unavailable" }, { status: 502 });
  }
}