/** Short-lived browser mutation tokens bound to an authenticated Clerk session. */
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { AccessError, type Principal } from "./policy.ts";

const TTL_MS = 10 * 60_000;
const TOKEN_FORMAT = /^(\d{13})\.([A-Za-z0-9_-]{32})\.([a-f0-9]{64})$/;

export const needsCsrf = (method: string) => ["POST", "PUT", "PATCH", "DELETE"].includes(method);

function signature(site: string, actor: Principal, secret: string, payload: string): Buffer {
  if (!actor.sessionId) throw new AccessError(401, "invalid_session");
  if (Buffer.byteLength(secret) < 32) throw new AccessError(503, "workspace_csrf_not_configured");
  const scope = JSON.stringify(["workspace-csrf-v1", site, actor.sessionId, actor.userId, actor.orgId, payload]);
  return createHmac("sha256", secret).update(scope).digest();
}

export function issueCsrf(site: string, actor: Principal, secret: string, now = Date.now()): string {
  const payload = `${now + TTL_MS}.${randomBytes(24).toString("base64url")}`;
  return payload + "." + signature(site, actor, secret, payload).toString("hex");
}

export function verifyCsrf(token: string, site: string, actor: Principal, secret: string, now = Date.now()): void {
  const match = TOKEN_FORMAT.exec(token);
  if (!match || Number(match[1]) <= now || Number(match[1]) > now + TTL_MS ||
      !timingSafeEqual(signature(site, actor, secret, match[1] + "." + match[2]), Buffer.from(match[3], "hex"))) {
    throw new AccessError(403, "invalid_csrf_token");
  }
}
