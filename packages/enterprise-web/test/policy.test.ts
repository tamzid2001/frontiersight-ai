import { test } from "node:test";
import assert from "node:assert/strict";
import { AccessError, assertOrganization, requireExpectedVersion, requireFeature, requirePrincipal,
  requireWorkspaceAdmin, tenantScope, validatePayload, type Principal } from "../src/policy.ts";

const member: Principal = { userId: "user_a", orgId: "org_a", orgRole: "org:member", features: ["api_access"] };

test("tenant scope binds product, active organization and actor independently", () => {
  assert.deepEqual(tenantScope("tool-firewall", member), {
    siteId: "tool-firewall", tenantKind: "organization", tenantId: "org_a", actorId: "user_a",
  });
  assert.notDeepEqual(tenantScope("tool-firewall", member), tenantScope("approval-ledger", member));
  assert.notDeepEqual(tenantScope("tool-firewall", member), tenantScope("tool-firewall", { ...member, orgId: "org_b" }));
  assert.equal(tenantScope("tool-firewall", { ...member, orgId: null }).tenantId, "user_a");
  assert.ok(Object.isFrozen(tenantScope("tool-firewall", member)));
});

test("client-selected organization and missing identity never confer access", () => {
  assert.throws(() => assertOrganization(member, "org_b"), { code: "organization_mismatch", status: 403 });
  assert.throws(() => assertOrganization({ ...member, orgId: null }, "org_a"), AccessError);
  assert.doesNotThrow(() => assertOrganization(member, "org_a"));
  for (const actor of [null, { ...member, userId: "" }, { ...member, orgId: "bad/tenant" }]) {
    assert.throws(() => requirePrincipal(actor), AccessError);
  }
  assert.throws(() => tenantScope("bad/site", member), { code: "invalid_site_configuration" });
});

test("paid capabilities and admin operations are enforced independently", () => {
  assert.equal(requireFeature(member, "api_access"), member);
  assert.throws(() => requireFeature(member, "export"), { status: 403 });
  assert.throws(() => requireWorkspaceAdmin(member), { code: "organization_admin_required" });
  assert.doesNotThrow(() => requireWorkspaceAdmin({ ...member, orgRole: "org:admin" }));
  assert.doesNotThrow(() => requireWorkspaceAdmin({ ...member, orgId: null, orgRole: null }));
  assert.throws(() => requirePrincipal({ ...member, features: ["client_supplied_pro"] as never }), AccessError);
});

test("optimistic mutations require a positive integral version", () => {
  assert.equal(requireExpectedVersion(1), 1);
  for (const value of [0, -1, 1.1, "1", true, null, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => requireExpectedVersion(value), { code: "expected_version_required" });
  }
});

test("JSON validation accepts domain data and rejects injection-shaped or unbounded inputs", () => {
  const value = { readings: [0, 1.5, null, true, "ok"] };
  assert.equal(validatePayload(value), value);
  assert.throws(() => validatePayload(JSON.parse('{"__proto__":{"admin":true}}')), { code: "reserved_payload_key" });
  for (const value of [[], null, "text", { x: NaN }, { x: () => 1 }, { x: new Date() }]) {
    assert.throws(() => validatePayload(value), AccessError);
  }
  const cyclic: Record<string, unknown> = {}; cyclic.x = cyclic;
  assert.throws(() => validatePayload(cyclic), { code: "repeated_or_cyclic_object" });
  assert.throws(() => validatePayload({ a: [1, 2] }, 2), { code: "payload_budget_exceeded" });
  let deep: unknown = {}; for (let i = 0; i < 10; i++) deep = { child: deep };
  assert.throws(() => validatePayload(deep), { code: "payload_budget_exceeded" });
  assert.throws(() => validatePayload({}, 0), { code: "invalid_payload_budget" });
});
