// Server-only helper for talking to the FastAPI backend. BACKEND_URL has no
// NEXT_PUBLIC_ prefix, so it never reaches the browser bundle.

export type BackendMethod = "GET" | "POST" | "PUT" | "DELETE";

const ALLOWED_ROOTS = new Set(["employees", "ai-twins", "integrations", "projects", "plane"]);
const SAFE_SEGMENT = /^[A-Za-z0-9_-]+$/;

export function isAllowedBackendPath(segments: string[]): boolean {
  return segments.length > 0 && ALLOWED_ROOTS.has(segments[0]) && segments.every((s) => SAFE_SEGMENT.test(s));
}

export async function callBackend(
  segments: string[],
  method: BackendMethod,
  body?: string,
  search = "",
): Promise<{ status: number; text: string }> {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return { status: 500, text: JSON.stringify({ detail: "BACKEND_URL is not configured in frontend/.env.local" }) };
  }
  try {
    const res = await fetch(`${backendUrl}/api/${segments.join("/")}${search}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    return { status: res.status, text: await res.text() };
  } catch {
    return { status: 502, text: JSON.stringify({ detail: `Backend unreachable at ${backendUrl}` }) };
  }
}

export async function fetchBackendJson<T>(segments: string[], method: BackendMethod = "GET", body?: unknown) {
  const { status, text } = await callBackend(segments, method, body === undefined ? undefined : JSON.stringify(body));
  try {
    const data = JSON.parse(text);
    if (status >= 200 && status < 300) return { data: data as T, error: null };
    return { data: null, error: typeof data?.detail === "string" ? data.detail : `Backend returned HTTP ${status}` };
  } catch {
    return { data: null, error: `Backend returned an unreadable response (HTTP ${status})` };
  }
}
