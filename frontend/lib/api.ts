const AI_BASE = process.env.AI_SERVICE_URL ?? "http://localhost:8000";

export async function apiEnroll(formData: FormData) {
  const res = await fetch(`${AI_BASE}/api/v1/enroll`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Enroll failed");
  }
  return res.json();
}

export async function apiVerify(formData: FormData) {
  const res = await fetch(`${AI_BASE}/api/v1/verify`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Verification failed");
  }
  return res.json();
}

export async function apiSearch(formData: FormData) {
  const res = await fetch(`${AI_BASE}/api/v1/search`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Search failed");
  }
  return res.json();
}

export async function apiSpeakers() {
  const res = await fetch(`${AI_BASE}/api/v1/speakers`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch speakers");
  return res.json();
}
