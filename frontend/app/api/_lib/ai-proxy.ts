import { NextRequest } from "next/server";

const AI_BASE = process.env.AI_SERVICE_URL ?? "http://localhost:8000";

function normalizeIpToken(value: string | null): string {
  const token = value?.trim().replace(/^"|"$/g, "") ?? "";
  if (!token || token.toLowerCase() === "unknown") return "";

  if (token.startsWith("[")) {
    const end = token.indexOf("]");
    return end >= 0 ? token.slice(1, end) : token.slice(1);
  }

  if (/^\d+\.\d+\.\d+\.\d+:\d+$/.test(token)) {
    return token.split(":")[0] ?? "";
  }

  return token;
}

function getForwardedForCandidates(value: string | null): string[] {
  if (!value) return [];

  return value
    .split(",")
    .map((segment) => normalizeIpToken(segment))
    .filter(Boolean);
}

function isInternalIp(value: string): boolean {
  const ipv4 = value.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4) {
    const first = Number(ipv4[1]);
    const second = Number(ipv4[2]);

    return (
      first === 10 ||
      first === 127 ||
      (first === 169 && second === 254) ||
      (first === 172 && second >= 16 && second <= 31) ||
      (first === 192 && second === 168) ||
      (first === 100 && second >= 64 && second <= 127)
    );
  }

  const lowered = value.toLowerCase();
  return (
    lowered === "::1" ||
    lowered === "::" ||
    lowered.startsWith("fc") ||
    lowered.startsWith("fd") ||
    lowered.startsWith("fe80:")
  );
}

function pickBestClientIp(candidates: Array<string | null | undefined>): string {
  const normalized = candidates
    .map((candidate) => normalizeIpToken(candidate ?? null))
    .filter(Boolean);

  return normalized.find((candidate) => !isInternalIp(candidate)) ?? normalized[0] ?? "";
}

function getIpFromForwardedHeader(value: string | null): string {
  if (!value) return "";

  for (const segment of value.split(",")) {
    const match = segment.match(/for=([^;]+)/i);
    if (!match) continue;

    const token = normalizeIpToken(match[1]);
    if (!token) continue;

    return token;
  }

  return "";
}

export function getForwardedClientIp(request: NextRequest): string {
  const cfConnectingIp = normalizeIpToken(request.headers.get("cf-connecting-ip"));
  const realIp = normalizeIpToken(request.headers.get("x-real-ip"));
  const forwardedForCandidates = getForwardedForCandidates(
    request.headers.get("x-forwarded-for"),
  );
  const forwardedIp = getIpFromForwardedHeader(request.headers.get("forwarded"));

  return pickBestClientIp([
    cfConnectingIp,
    ...forwardedForCandidates,
    forwardedIp,
    realIp,
  ]);
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