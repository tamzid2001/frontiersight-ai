/** Bounded Web-standard HTTP utilities, shared by API and MCP adapters. */
import { randomUUID } from "node:crypto";
import { AccessError, validatePayload } from "./policy.ts";

export function jsonResponse(value: unknown, status = 200, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(value), { status, headers: {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    ...extraHeaders,
  } });
}

export function errorResponse(error: unknown): Response {
  const id = randomUUID();
  const status = error instanceof AccessError ? error.status : 503;
  const code = error instanceof AccessError ? error.code : "service_unavailable";
  return jsonResponse({ error: { code, requestId: id } }, status,
    status === 429 ? { "retry-after": "60", "x-request-id": id } : { "x-request-id": id });
}

export function enforceOrigin(request: Request, allowed: readonly string[]) {
  const origin = request.headers.get("origin");
  if (origin && !allowed.includes(origin)) throw new AccessError(403, "request_origin_not_allowed");
}

export async function readJson(request: Request, maximumBytes = 256 * 1024): Promise<Record<string, unknown>> {
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes < 1 || maximumBytes > 1024 * 1024) {
    throw new AccessError(500, "invalid_body_budget");
  }
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get("content-type") ?? "")) {
    throw new AccessError(415, "json_content_type_required");
  }
  if (!request.body) throw new AccessError(400, "json_body_required");
  const reader = request.body.getReader(), parts: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      if (request.signal.aborted) throw new AccessError(400, "request_aborted");
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximumBytes) throw new AccessError(413, "request_body_too_large");
      parts.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  let parsed: unknown;
  try { parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
  catch { throw new AccessError(400, "invalid_json"); }
  return validatePayload(parsed);
}

export function strictFields(value: Record<string, unknown>, allowed: readonly string[]) {
  if (Object.keys(value).some(key => !allowed.includes(key))) throw new AccessError(400, "unexpected_request_field");
}

export function pageSize(value: string | null, maximum = 100): number {
  if (value === null) return Math.min(50, maximum);
  if (!/^[0-9]{1,3}$/.test(value)) throw new AccessError(400, "invalid_page_size");
  const size = Number(value);
  if (size < 1 || size > maximum) throw new AccessError(400, "invalid_page_size");
  return size;
}
