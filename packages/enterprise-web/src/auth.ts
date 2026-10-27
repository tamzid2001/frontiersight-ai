/** Official Clerk verification for bearer-authenticated server APIs.
 * Request data never supplies subject IDs, organization roles or entitlements.
 */
import { createClerkClient } from "@clerk/backend";
import { AccessError, type Feature, type Principal, requirePrincipal } from "./policy.ts";

export type ClerkConfiguration = Readonly<{
  publishableKey: string;
  secretKey: string;
  jwtKey?: string;
  issuer: string;
  authorizedParties: readonly string[];
}>;

const FEATURE_NAMES: readonly Feature[] = ["analytics", "export", "api_access", "audit_logs", "priority_support"];

export function clerkConfiguration(env: NodeJS.ProcessEnv): ClerkConfiguration {
  const publishableKey = env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() ?? "";
  const secretKey = env.CLERK_SECRET_KEY?.trim();
  const jwtKey = env.CLERK_JWT_KEY?.replace(/\\n/g, "\n").trim();
  const issuer = env.CLERK_ISSUER?.trim() ?? "";
  const authorizedParties = (env.CLERK_AUTHORIZED_PARTIES ?? "").split(",").map(x => x.trim()).filter(Boolean);
  if (!publishableKey || !secretKey || !issuer || !authorizedParties.length) {
    throw new AccessError(503, "authentication_not_configured");
  }
  for (const value of [issuer, ...authorizedParties]) {
    let url: URL;
    try { url = new URL(value); } catch { throw new AccessError(503, "invalid_authentication_origin"); }
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (url.origin !== value || (url.protocol !== "https:" && !(local && env.NODE_ENV !== "production"))) {
      throw new AccessError(503, "invalid_authentication_origin");
    }
  }
  return Object.freeze({ publishableKey, secretKey, jwtKey, issuer,
    authorizedParties: Object.freeze([...new Set(authorizedParties)]) });
}

export function createBearerAuthenticator(configuration: ClerkConfiguration) {
  const client = createClerkClient({ publishableKey: configuration.publishableKey,
    secretKey: configuration.secretKey, jwtKey: configuration.jwtKey,
    telemetry: { disabled: true } });
  return async function authenticate(request: Request): Promise<Principal> {
    const authorization = request.headers.get("authorization") ?? "";
    if (!/^Bearer [^\s]{20,16384}$/i.test(authorization)) {
      throw new AccessError(401, "authentication_required");
    }
    let state;
    try {
      state = await client.authenticateRequest(request, {
        acceptsToken: "session_token",
        authorizedParties: [...configuration.authorizedParties],
        jwtKey: configuration.jwtKey,
        clockSkewInMs: 1000,
      });
    } catch {
      // Provider details and raw tokens must never reach responses or logs.
      throw new AccessError(401, "invalid_session");
    }
    if (!state.isAuthenticated || state.tokenType !== "session_token") {
      throw new AccessError(401, "invalid_session");
    }
    const verified = state.toAuth();
    if (!verified.userId || verified.sessionClaims.iss !== configuration.issuer
        || !configuration.authorizedParties.includes(verified.sessionClaims.azp ?? "")) {
      throw new AccessError(401, "invalid_session_origin");
    }
    if (verified.orgId && !verified.orgRole) throw new AccessError(401, "invalid_organization_identity");
    // Bare Clerk feature slugs can match either user or organization plans.
    // Pin the active billing entity so personal Pro never upgrades a free org.
    const prefix = verified.orgId ? "org:" : "user:";
    const features = FEATURE_NAMES.filter(feature => verified.has({ feature: prefix + feature }));
    const plan = (["enterprise", "pro", "starter"] as const).find(name => verified.has({ plan: prefix + name })) ?? "free";
    const principal = Object.freeze({ userId: verified.userId, orgId: verified.orgId ?? null,
      orgRole: verified.orgRole ?? null, plan, features: Object.freeze(features) });
    return requirePrincipal(principal);
  };
}
