import { NextRequest } from "next/server";

const AI_BASE = process.env.AI_SERVICE_URL ?? "http://localhost:8000";

function getFirstForwardedIp(value: string | null): string {
  return value?.split(",")[0]?.trim() ?? "";
}

function getIpFromForwardedHeader(value: string | null): string {
  if (!value) return "";

  for (const segment of value.split(",")) {
    const match = segment.match(/for=([^;]+)/i);
    if (!match) continue;

    const token = match[1].trim().replace(/^"|"$/g, "");
    if (!token || token.toLowerCase() === "unknown") continue;

    if (token.startsWith("[")) {
      const end = token.indexOf("]");
      return end >= 0 ? token.slice(1, end) : token.slice(1);
    }

    if (/^\d+\.\d+\.\d+\.\d+:\d+$/.test(token)) {
      return token.split(":")[0] ?? "";
    }

    return token;
  }

  return "";
}

export function getForwardedClientIp(request: NextRequest): string {
  const realIp = request.headers.get("x-real-ip")?.trim();
  if (realIp) return realIp;

  const cfConnectingIp = request.headers.get("cf-connecting-ip")?.trim();
  if (cfConnectingIp) return cfConnectingIp;

  const forwardedIp = getIpFromForwardedHeader(request.headers.get("forwarded"));
  if (forwardedIp) return forwardedIp;

  return getFirstForwardedIp(request.headers.get("x-forwarded-for"));
}

export function buildAiProxyHeaders(
  request: NextRequest,
  init?: HeadersInit,
): Headers {
  const headers = new Headers(init);
  const forwardedFor = request.headers.get("x-forwarded-for")?.trim();
  const forwarded = request.headers.get("forwarded")?.trim();
  const forwardedIp = getIpFromForwardedHeader(forwarded ?? null);
  const clientIp = getForwardedClientIp(request);
  const upstreamForwardedFor = forwardedFor || forwardedIp || clientIp;

  if (upstreamForwardedFor) {
    headers.set("x-forwarded-for", upstreamForwardedFor);
    headers.set("x-voiceprint-forwarded-for", upstreamForwardedFor);
  }
  if (clientIp) {
    headers.set("x-real-ip", clientIp);
    headers.set("x-voiceprint-client-ip", clientIp);
  }

  if (forwarded) {
    headers.set("forwarded", forwarded);
  }

  const userAgent = request.headers.get("user-agent");
  if (userAgent && !headers.has("user-agent")) {
    headers.set("user-agent", userAgent);
  }

  return headers;
}

export function aiUrl(path: string): string {
  return `${AI_BASE}${path}`;
}