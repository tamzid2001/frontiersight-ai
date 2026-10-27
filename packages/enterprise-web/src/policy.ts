/** Pure authorization contracts. Call only with server-verified Clerk identity.
 * This module does not verify tokens. HTTP adapters must authenticate first;
 * never construct a Principal from JSON, headers containing user IDs, or UI state.
 */
export type Feature = "analytics" | "export" | "api_access" | "audit_logs" | "priority_support";
export type Principal = Readonly<{
  userId: string;
  orgId: string | null;
  orgRole: string | null;
  plan?: "free" | "starter" | "pro" | "enterprise";
  features: readonly Feature[];
}>;

export class AccessError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string) {
    super(code);
    this.name = "AccessError";
    this.status = status;
    this.code = code;
  }
}

const IDENTIFIER = /^[A-Za-z][A-Za-z0-9_-]{0,127}$/;
const SITE_ID = /^[a-z][a-z0-9-]{1,79}$/;
const FEATURES: ReadonlySet<string> = new Set([
  "analytics", "export", "api_access", "audit_logs", "priority_support",
]);

export function requirePrincipal(value: Principal | null): Principal {
  if (!value || !IDENTIFIER.test(value.userId)) throw new AccessError(401, "authentication_required");
  if (value.orgId !== null && !IDENTIFIER.test(value.orgId)) {
    throw new AccessError(401, "invalid_organization_identity");
  }
  if (!Array.isArray(value.features) || value.features.some(feature => !FEATURES.has(feature))) {
    throw new AccessError(401, "invalid_entitlement_context");
  }
  if (value.plan !== undefined && !["free", "starter", "pro", "enterprise"].includes(value.plan)) {
    throw new AccessError(401, "invalid_plan_context");
  }
  return value;
}

/** Namespace every persisted row by product AND active verified tenant. */
export function tenantScope(siteId: string, principal: Principal | null) {
  if (!SITE_ID.test(siteId)) throw new AccessError(500, "invalid_site_configuration");
  const actor = requirePrincipal(principal);
  return Object.freeze({
    siteId,
    tenantKind: actor.orgId ? "organization" : "user",
    tenantId: actor.orgId ?? actor.userId,
    actorId: actor.userId,
  });
}

/** A requested organization is a constraint, never a tenant-selection authority. */
export function assertOrganization(principal: Principal | null, requestedId: string): void {
  const actor = requirePrincipal(principal);
  if (!actor.orgId || actor.orgId !== requestedId) throw new AccessError(403, "organization_mismatch");
}

export function requireFeature(principal: Principal | null, feature: Feature): Principal {
  const actor = requirePrincipal(principal);
  if (!FEATURES.has(feature) || !actor.features.includes(feature)) {
    throw new AccessError(403, "feature_not_in_plan");
  }
  return actor;
}

export function requireWorkspaceAdmin(principal: Principal | null): Principal {
  const actor = requirePrincipal(principal);
  // Personal workspaces belong to their user. Org mutations require the signed
  // default administrator role; UI visibility alone never authorizes a mutation.
  if (actor.orgId && actor.orgRole !== "org:admin") {
    throw new AccessError(403, "organization_admin_required");
  }
  return actor;
}

export function requireExpectedVersion(value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) < 1) {
    throw new AccessError(400, "expected_version_required");
  }
  return value as number;
}

/** Accept one bounded JSON object and reject ambiguous or resource-heavy shapes. */
export function validatePayload(value: unknown, maxNodes = 10_000): Record<string, unknown> {
  if (!Number.isSafeInteger(maxNodes) || maxNodes < 1 || maxNodes > 50_000) {
    throw new AccessError(500, "invalid_payload_budget");
  }
  const stack: [unknown, number][] = [[value, 0]];
  const seen = new Set<object>();
  let count = 0;
  while (stack.length) {
    const [item, depth] = stack.pop()!;
    if (++count > maxNodes || depth > 8) throw new AccessError(400, "payload_budget_exceeded");
    if (typeof item === "number" && !Number.isFinite(item)) {
      throw new AccessError(400, "nonfinite_number");
    }
    if (item && typeof item === "object") {
      if (seen.has(item)) throw new AccessError(400, "repeated_or_cyclic_object");
      seen.add(item);
      if (!Array.isArray(item) && Object.getPrototypeOf(item) !== Object.prototype && Object.getPrototypeOf(item) !== null) {
        throw new AccessError(400, "plain_json_objects_required");
      }
      for (const [key, child] of Object.entries(item)) {
        if (["__proto__", "constructor", "prototype"].includes(key)) {
          throw new AccessError(400, "reserved_payload_key");
        }
        stack.push([child, depth + 1]);
      }
    } else if (!["string", "number", "boolean"].includes(typeof item) && item !== null) {
      throw new AccessError(400, "unsupported_payload_value");
    }
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new AccessError(400, "json_object_required");
  }
  return value as Record<string, unknown>;
}
