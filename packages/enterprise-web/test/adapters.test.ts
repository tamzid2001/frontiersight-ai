import { test, after } from "node:test";
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { workspaceServer } from "../src/server.ts";
import { workspaceOpenApi } from "../src/openapi.ts";
import { createSupportHandler, helpAnswer } from "../src/support.ts";
import { firestoreClient } from "../src/firestore.ts";
import { createBearerAuthenticator } from "../src/auth.ts";
import { config, origin, token } from "./auth.fixture.ts";

const site = { siteId: "adapter-" + randomBytes(6).toString("hex"), name: "Adapters", stages: ["Open", "Done"], origins: [origin] };
test("server adapters fail safely without configuration, including MCP and support", async () => {
  const server = workspaceServer(site, {});
  for (const call of [server.api, server.mcp, server.support]) {
    const response = await call(new Request(origin));
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error.code, "authentication_not_configured");
  }
});
test("OpenAPI is specific to this product, covers implemented operations and requires authentication", () => {
  const spec = workspaceOpenApi(site, origin);
  assert.equal(spec.openapi, "3.1.0"); assert.equal(spec.info.title, "Adapters workspace API");
  assert.equal(Object.keys(spec.paths).length, 5);
  assert.equal(spec.paths["/api/v1/workflows"].post.parameters[0].required, true);
  assert.equal(spec.components.schemas.Record.properties.stage.maximum, 1);
  assert.deepEqual(spec.security, [{ ClerkSession: [] }]);
  assert.throws(() => workspaceOpenApi(site, origin + "/path"));
});
test("local support answers distinguish billing, organization, API, saved records and general help", () => {
  for (const [question, expected] of [["billing", "first annual"], ["members", "administrators"],
    ["MCP", "api_access"], ["saved records", "Firestore"], ["hello", "/contact"]]) assert.ok(helpAnswer(question).includes(expected));
});

const emulator = process.env.FIRESTORE_EMULATOR_HOST;
const db = emulator ? firestoreClient({ FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_EMULATOR_HOST: emulator }) : null;
after(async () => { if (db) await db.terminate(); });
const deps = { database: () => db!, authenticate: createBearerAuthenticator(config), auditSecret: randomBytes(32).toString("hex") };
function request(body: unknown = { question: "How do saved records work?" }) {
  return new Request(origin + "/api/support", { method: "POST", headers: { authorization: "Bearer " + token(), "content-type": "application/json" }, body: JSON.stringify(body) });
}
test("support is authenticated, bounded and never calls an unverified provider", { skip: !emulator }, async () => {
  const handler = createSupportHandler(site, deps, {}, async () => { throw Error("provider must not run"); });
  const response = await handler(request());
  assert.equal(response.status, 200); assert.equal((await response.json()).mode, "documentation");
  assert.equal((await handler(request({ question: "x".repeat(1001) }))).status, 400);
  assert.equal((await handler(request({ question: "hi", userId: "user_victim" }))).status, 400);
  assert.equal((await handler(new Request(origin))).status, 401);
});
test("explicitly enabled free provider receives only a bounded question and documentation context", { skip: !emulator }, async () => {
  let calls = 0;
  const env = { SUPPORT_AI_FREE_ENDPOINT_VERIFIED: "true", SUPPORT_AI_MODEL: "test/free-model", NVIDIA_API_KEY: "test-only-not-a-real-key" };
  const handler = createSupportHandler({ ...site, siteId: site.siteId + "-ai" }, deps, env, async (url, init) => {
    calls++; assert.equal(url, "https://integrate.api.nvidia.com/v1/chat/completions");
    const body = JSON.parse(init!.body as string);
    assert.equal(body.max_tokens, 512); assert.equal(body.messages.length, 2);
    assert.ok(!JSON.stringify(body).includes("user_alice"));
    return Response.json({ choices: [{ message: { content: "Use /workflows to save records." } }] });
  });
  assert.equal((await (await handler(request())).json()).mode, "ai"); assert.equal(calls, 1);
  const offline = createSupportHandler({ ...site, siteId: site.siteId + "-offline" }, deps, env,
    async () => { throw Error("provider offline"); });
  assert.equal((await (await offline(request())).json()).mode, "documentation");
});

test("lazy server adapters execute against the emulator with verified sessions and close connections", { skip: !emulator }, async () => {
  const server = workspaceServer({ ...site, siteId: site.siteId + "-server" }, {
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: config.publishableKey, CLERK_SECRET_KEY: config.secretKey,
    CLERK_JWT_KEY: config.jwtKey, CLERK_ISSUER: config.issuer, CLERK_AUTHORIZED_PARTIES: origin,
    FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_EMULATOR_HOST: emulator,
    WORKSPACE_AUDIT_SECRET: deps.auditSecret,
  });
  try {
    assert.equal((await server.api(new Request(origin + "/api/workspace", { headers: { authorization: "Bearer " + token() } }))).status, 200);
    assert.equal((await server.support(request())).status, 200);
    assert.equal((await server.mcp(new Request(origin + "/api/mcp", { headers: { authorization: "Bearer " + token() } }))).status, 405);
  } finally { await server.close(); }
  await server.close();
});
