import { test } from "node:test";
import assert from "node:assert/strict";
import { clerkConfiguration, createBearerAuthenticator } from "../src/auth.ts";
import { requireFeature, requireWorkspaceAdmin } from "../src/policy.ts";

import { config, issuer, origin, token, request } from "./auth.fixture.ts";
const authenticate = createBearerAuthenticator(config);

function forgedToken() {
  const parts = token().split(".");
  parts[2] = (parts[2][0] === "A" ? "B" : "A") + parts[2].slice(1);
  return parts.join(".");
}

test("actual Clerk SDK verifies an RSA-signed session and derives immutable personal features", async () => {
  const actor = await authenticate(request());
  assert.equal(actor.userId, "user_alice"); assert.equal(actor.orgId, null);
  assert.equal(requireFeature(actor, "export"), actor);
  assert.ok(Object.isFrozen(actor)); assert.ok(Object.isFrozen(actor.features));
});

test("personal paid features cannot grant access to an active free organization", async () => {
  const actor = await authenticate(request(token({ o: { id: "org_acme", rol: "member", slg: "acme" },
    pla: "u:pro,o:free", fea: "u:api_access,u:export" })));
  assert.equal(actor.orgId, "org_acme"); assert.equal(actor.orgRole, "org:member");
  assert.throws(() => requireFeature(actor, "export"), { status: 403 });
  assert.throws(() => requireWorkspaceAdmin(actor), { status: 403 });
  const admin = await authenticate(request(token({ o: { id: "org_acme", rol: "admin", slg: "acme" },
    pla: "o:pro", fea: "o:api_access,o:export" })));
  assert.doesNotThrow(() => requireFeature(admin, "api_access"));
  assert.doesNotThrow(() => requireWorkspaceAdmin(admin));
});

test("expired, wrong-origin, wrong-issuer and forged sessions fail closed", async () => {
  const now = Math.floor(Date.now() / 1000);
  for (const value of [token({ exp: now - 60 }), token({ azp: "https://evil.example" }),
    token({ iss: "https://other.clerk.accounts.dev" }), token({ azp: undefined }),
    forgedToken()]) {
    await assert.rejects(authenticate(request(value)), { status: 401 });
  }
  await assert.rejects(authenticate(new Request(origin)), { code: "authentication_required" });
});

test("configuration needs explicit trusted origins and never silently uses a default account", () => {
  assert.throws(() => clerkConfiguration({}), { status: 503 });
  const env = { NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: config.publishableKey, CLERK_JWT_KEY: config.jwtKey,
    CLERK_SECRET_KEY: config.secretKey,
    CLERK_ISSUER: issuer, CLERK_AUTHORIZED_PARTIES: origin, NODE_ENV: "production" };
  assert.equal(clerkConfiguration(env).authorizedParties[0], origin);
  for (const value of ["https://tool-firewall.example/path", "not a URL", "http://tool-firewall.example", "http://localhost:3000"]) {
    assert.throws(() => clerkConfiguration({ ...env, CLERK_AUTHORIZED_PARTIES: value }), { status: 503 });
  }
  assert.equal(clerkConfiguration({ ...env, NODE_ENV: "test", CLERK_AUTHORIZED_PARTIES: "http://localhost:3000" }).authorizedParties.length, 1);
});
