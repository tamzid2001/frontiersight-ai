import { test } from "node:test";
import assert from "node:assert/strict";
import { enforceOrigin, errorResponse, jsonResponse, pageSize, readJson, strictFields } from "../src/http.ts";
import { AccessError } from "../src/policy.ts";

function req(body: BodyInit, headers = { "content-type": "application/json" }) {
  return new Request("https://example.test/api", { method: "POST", body, headers });
}

test("JSON reads check actual bytes, not a forged Content-Length", async () => {
  assert.deepEqual(await readJson(req('{"hello":"world"}')), { hello: "world" });
  await assert.rejects(readJson(req('{"long":"' + "x".repeat(200) + '"}',
    { "content-type": "application/json", "content-length": "1" }), 64), { status: 413 });
  await assert.rejects(readJson(req("{invalid}")), { code: "invalid_json" });
  await assert.rejects(readJson(req("[]")), { code: "json_object_required" });
  await assert.rejects(readJson(req('{"__proto__":{}}')), { code: "reserved_payload_key" });
  await assert.rejects(readJson(req(new Uint8Array([0xff]))), { code: "invalid_json" });
  await assert.rejects(readJson(req("{}", { "content-type": "text/plain" })), { status: 415 });
  await assert.rejects(readJson(new Request("https://example.test", { method: "POST", headers: { "content-type": "application/json" } })), { code: "json_body_required" });
  await assert.rejects(readJson(req("{}"), 0), { status: 500 });
});

test("aborted bodies fail and release their reader", async () => {
  const abort = new AbortController(); abort.abort();
  const request = new Request("https://example.test", { method: "POST", body: "{}", signal: abort.signal,
    headers: { "content-type": "application/json" } });
  await assert.rejects(readJson(request), { code: "request_aborted" });
  assert.equal(request.body!.locked, false);
});

test("private responses cannot be cached and provider errors cannot expose secrets", async () => {
  const response = jsonResponse({ ok: true });
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("vary"), "Authorization");
  assert.equal(errorResponse(new AccessError(429, "quota_exhausted")).headers.get("retry-after"), "60");
  const text = await errorResponse(new Error("private customer payload and secret")).text();
  assert.equal(text.includes("private customer"), false);
  assert.equal(JSON.parse(text).error.code, "service_unavailable");
});

test("origin, field and pagination guards reject ambiguous requests", () => {
  assert.doesNotThrow(() => enforceOrigin(new Request("https://example.test"), ["https://example.test"]));
  assert.throws(() => enforceOrigin(new Request("https://example.test", { headers: { origin: "https://evil.example" } }), ["https://example.test"]), { status: 403 });
  assert.doesNotThrow(() => strictFields({ title: "x" }, ["title"]));
  assert.throws(() => strictFields({ role: "admin" }, ["title"]), { code: "unexpected_request_field" });
  assert.equal(pageSize(null), 50); assert.equal(pageSize(null, 10), 10); assert.equal(pageSize("2"), 2);
  for (const value of ["-1", "0", "1e2", "101", "1.5"]) assert.throws(() => pageSize(value));
});
