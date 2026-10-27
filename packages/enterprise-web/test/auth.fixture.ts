import { generateKeyPairSync, createSign, randomBytes } from "node:crypto";
// Fresh test-only key material is generated at runtime, never a live Clerk key.
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
export const issuer = "https://test-quantura.clerk.accounts.dev";
export const origin = "https://tool-firewall.example";
export const config = { publishableKey: "pk_test_" + Buffer.from("test-quantura.clerk.accounts.dev$").toString("base64"),
  secretKey: "sk_test_" + randomBytes(32).toString("base64url"),
  jwtKey: publicKey.export({ type: "spki", format: "pem" }).toString(), issuer, authorizedParties: [origin] };


export function token(extra: Record<string, unknown> = {}) {
  const now = Math.floor(Date.now() / 1000);
  const payload = { v: 2, iss: issuer, sub: "user_alice", sid: "sess_unit_test", azp: origin,
    iat: now - 1, nbf: now - 1, exp: now + 60, pla: "u:pro", fea: "u:api_access,u:export", ...extra };
  const input = [JSON.stringify({ alg: "RS256", typ: "JWT", kid: "unit-test" }), JSON.stringify(payload)]
    .map(x => Buffer.from(x).toString("base64url")).join(".");
  return input + "." + createSign("RSA-SHA256").update(input).sign(privateKey).toString("base64url");
}
export function request(value = token()) { return new Request(origin + "/api/analysis", { headers: { authorization: "Bearer " + value } }); }

