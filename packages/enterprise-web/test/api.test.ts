import { after, test } from "node:test";
import assert from "node:assert/strict";
import { randomBytes, randomUUID } from "node:crypto";
import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { firestoreClient, FirestoreWorkspace } from "../src/firestore.ts";
import { createWorkspaceApi, storagePolicy } from "../src/api.ts";
import { createWorkspaceMcp } from "../src/mcp.ts";
import { createBearerAuthenticator } from "../src/auth.ts";
import { config, origin, token } from "./auth.fixture.ts";

const emulator = process.env.FIRESTORE_EMULATOR_HOST;
const db = emulator ? firestoreClient({ FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_EMULATOR_HOST: emulator }) : null;
after(async () => { if (db) await db.terminate(); });
const site = { siteId: "api-test-" + randomBytes(6).toString("hex"), name: "API test", stages: ["Queued", "Reviewed", "Done"], origins: [origin] };
const deps = { database: () => db!, authenticate: createBearerAuthenticator(config), auditSecret: randomBytes(32).toString("hex") };
const api = createWorkspaceApi(site, deps);
function request(path = "", method = "GET", body?: unknown, jwt = token(), key = randomUUID()) {
  return new Request(origin + "/api/workspace" + path, { method, headers: {
    authorization: "Bearer " + jwt, "content-type": "application/json", "idempotency-key": key,
  }, body: body === undefined ? undefined : JSON.stringify(body) });
}

test("unauthenticated and cross-origin requests are rejected before database access", async () => {
  const noDatabase = createWorkspaceApi(site, { ...deps, database: () => { throw Error("must not access database"); } });
  assert.equal((await noDatabase(new Request(origin + "/api/workspace"))).status, 401);
  assert.equal((await noDatabase(new Request(origin + "/api/workspace", { headers: { origin: "https://evil.example" } }))).status, 403);
});

test("signed identity roundtrip, bounded list/export, idempotency and concurrency through HTTP", { skip: !emulator }, async () => {
  const input = { title: "HTTP saved record", payload: { check: [1, 2, 3] } }, key = randomUUID();
  const first = await api(request("", "POST", input, token(), key));
  assert.equal(first.status, 201); const row = await first.json();
  assert.equal((await api(request("", "POST", input, token(), key))).status, 200);
  const list = await (await api(request("?limit=1"))).json();
  assert.equal(list.items.length, 1); assert.equal("payload" in list.items[0], false);
  assert.equal(list.next, row.id);
  const page = await (await api(request("/export"))).json(); assert.deepEqual(page.items[0].payload, input.payload);
  assert.equal((await api(request("/" + row.id, "PATCH", { stage: 1, expectedVersion: 1 }))).status, 200);
  assert.equal((await api(request("/" + row.id, "PATCH", { stage: 2, expectedVersion: 1 }))).status, 409);
  assert.equal((await api(request("/" + row.id, "DELETE", { expectedVersion: 2 }))).status, 200);
  assert.equal((await api(request("/" + row.id))).status, 404);
});

test("HTTP rejects tenant selection, stale organization, elevated member deletes and free paid endpoints", { skip: !emulator }, async () => {
  const member = token({ o: { id: "org_team", rol: "member", slg: "team" }, pla: "o:pro", fea: "o:api_access" });
  assert.equal((await api(request("", "POST", { title: "Bad", payload: {}, orgId: "org_victim" }))).status, 400);
  const changed = request(); changed.headers.set("x-workspace-organization", "org_other");
  assert.equal((await api(changed)).status, 409);
  assert.equal((await api(request("/" + randomUUID(), "DELETE", { expectedVersion: 1 }, member))).status, 403);
  const free = token({ pla: "u:free", fea: "" });
  assert.equal((await api(request("/export", "GET", undefined, free))).status, 403);
  const developer = new Request(origin + "/api/v1/workflows", { headers: { authorization: "Bearer " + free } });
  assert.equal((await api(developer)).status, 403);
  assert.equal((await api(request("/context", "GET", undefined, free))).status, 200);
  assert.equal((await api(request("?limit=10000"))).status, 400);
  assert.equal((await api(request("", "POST", { title: "Invalid", payload: [] }))).status, 400);
  assert.equal((await api(request("/unknown"))).status, 405);
});

test("durable rate budget and signed audit detect alteration against the actual emulator", { skip: !emulator }, async () => {
  const principal = await deps.authenticate(request());
  const store = new FirestoreWorkspace(db!, site.siteId + "-audit", principal, storagePolicy(principal, 3), deps.auditSecret);
  await store.consumeRequest(1);
  await assert.rejects(store.consumeRequest(1), { code: "request_rate_limit" });
  assert.equal((await store.verifiedAuditPage()).complete, true);
  await store.create({ title: "Audit", payload: {} }, randomUUID());
  assert.equal((await store.verifiedAuditPage()).verifiedWindow, true);
  const ref = db!.doc(`quantura_web/${site.siteId}-audit/tenants/user_user_alice/audit/000000000001`);
  await ref.update({ operation: "forged" });
  await assert.rejects(store.verifiedAuditPage(), { code: "audit_integrity_error" });
});

test("actual MCP client negotiates the SDK protocol, calls tools and preserves tenant isolation", { skip: !emulator, timeout: 20_000 }, async () => {
  const mcp = createWorkspaceMcp({ ...site, siteId: site.siteId + "-mcp" }, deps);
  const client = new Client({ name: "integration-test", version: "1.0.0" });
  let jwt = token();
  const transport = new StreamableHTTPClientTransport(new URL(origin + "/api/mcp"), {
    fetch: async (input, init) => {
      const req = new Request(input, init); req.headers.set("authorization", "Bearer " + jwt);
      return mcp(req);
    },
  });
  try {
    await client.connect(transport);
    const tools = await client.listTools(); assert.equal(tools.tools.length, 4);
    const created = await client.callTool({ name: "create_workflow", arguments: { title: "MCP real save", payload: { sample: true }, idempotencyKey: randomUUID() } });
    assert.equal(created.isError, false);
    const row = JSON.parse((created.content as { text: string }[])[0].text);
    const listed = await client.callTool({ name: "list_workflows", arguments: { limit: 2 } });
    assert.equal(JSON.parse((listed.content as { text: string }[])[0].text).items[0].id, row.id);
    jwt = token({ sub: "user_someone_else" });
    const isolated = await client.callTool({ name: "list_workflows", arguments: {} });
    assert.deepEqual(JSON.parse((isolated.content as { text: string }[])[0].text).items, []);
  } finally { await client.close(); }
  const denied = await mcp(new Request(origin + "/api/mcp", { method: "POST", headers: {
    authorization: "Bearer " + token({ fea: "", pla: "u:free" }), "content-type": "application/json" }, body: "{}" }));
  assert.equal(denied.status, 403);
});
