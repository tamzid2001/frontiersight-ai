import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import test from "node:test";
import { createWorkspaceApi } from "../src/api.ts";
import { createBearerAuthenticator } from "../src/auth.ts";
import { runAnalysis } from "../src/analysis.ts";
import { issueCsrf, verifyCsrf } from "../src/csrf.ts";
import { readJsonUpload, uploadName } from "../src/upload.ts";
import { config, origin, token } from "./auth.fixture.ts";

const site = { siteId: "atmospheric-calibrated-forecast-platform", name: "Calibration", stages: ["Ready"], origins: [origin] };
const secret = randomBytes(32).toString("hex");
const principal = { sessionId: "sess_unit_test", userId: "user_alice", orgId: null, orgRole: null, features: [] };
const workspace = createWorkspaceApi(site, { auditSecret: secret, authenticate: createBearerAuthenticator(config),
  database: () => { throw Error("The policy should respond before accessing storage."); } });
const base = origin + "/api/workspace";

test("workspace mutations require a CSRF token matched to the verified session before storage access", async () => {
  const authorization = "Bearer " + token();
  const challenge = await workspace(new Request(base + "/csrf", { headers: { authorization } }));
  const { token: csrf } = await challenge.json();
  assert.equal(challenge.headers.get("cache-control"), "no-store");
  assert.doesNotThrow(() => verifyCsrf(csrf, site.siteId, principal, secret));
  for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
    const missing = await workspace(new Request(base, { method, headers: { authorization } }));
    assert.equal((await missing.json()).error.code, "invalid_csrf_token");
  }
  const crossSession = await workspace(new Request(base, { method: "POST", headers: {
    authorization: "Bearer " + token({ sid: "sess_another" }), "x-csrf-token": csrf,
  } }));
  assert.equal((await crossSession.json()).error.code, "invalid_csrf_token");
  const expired = issueCsrf(site.siteId, principal, secret, Date.now() - 10 * 60_000);
  assert.throws(() => verifyCsrf(expired, site.siteId, principal, secret), { code: "invalid_csrf_token" });
});

test("real Clerk token validation rejects expired login state before issuing an action token", async () => {
  const response = await workspace(new Request(base + "/csrf", {
    headers: { authorization: "Bearer " + token({ exp: Math.floor(Date.now() / 1000) - 60 }) },
  }));
  assert.equal(response.status, 401);
  assert.equal((await response.json()).error.code, "invalid_session");
});

test("a bounded UTF-8 forecast file feeds the existing calibration analyzer", async () => {
  const dates = ["2026-01-02T10:00:00Z", "2026-01-02T11:00:00Z"];
  const input = new File([JSON.stringify({ unit: "°C",
    forecasts: dates.map((at, index) => ({ at, p10: 8, p50: [10, 12][index], p90: 13 })),
    observations: dates.map((at, index) => ({ at, value: [11, 12][index] })),
  })], "../Forecast run.json");
  const file = await readJsonUpload(input, 1024);
  assert.equal(file.name, "Forecast_run.json");
  assert.equal(runAnalysis(site.siteId, JSON.parse(file.text)).metrics["Median forecast MAE"], 0.5);
  await assert.rejects(readJsonUpload(input, 5), /nonempty JSON file/);
  await assert.rejects(readJsonUpload(new File(["{}"], "forecast.exe"), 1024), /approved file type/);
  await assert.rejects(readJsonUpload(new File([new Uint8Array([255])], "bad.json"), 1024), /encoded data/);
  assert.throws(() => uploadName(".json", new Set([".json"])), /approved file type/);
});
