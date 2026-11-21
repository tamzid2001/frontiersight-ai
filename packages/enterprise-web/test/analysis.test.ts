import { test } from "node:test";
import assert from "node:assert/strict";
import { analysisGuide, comparePixels, getAnalysis, MAX_INPUT_BYTES, parseInput, runAnalysis } from "../src/analysis.ts";
import { loadPublicSource } from "../src/analysis-sources.ts";
import { workspaceOpenApi } from "../src/openapi.ts";

const expected = {
  "multicloud-agent-control-plane": { Gate: "Hold", "Error increase (percentage points)": 0.9 },
  "agent-tool-permission-firewall": { Requests: 2, Denied: 1 },
  "mcp-tool-observability-hub": { Calls: 2, "p95 latency (ms)": 100 },
  "agent-human-approval-ledger": { "Record status": "Insufficient approvals" },
  "multiagent-workflow-engine": { "Critical path (ms)": 160 },
  "distributed-debugging-bench": { "Critical path (ms)": 160 },
  "agent-evaluation-orchestrator": { "True positives": 1, "False positives": 1, "Brier score": 0.2066666667 },
  "flaky-test-forensics": { "Mixed groups": 1 },
  "production-incident-replay-lab": { "Recovery (seconds)": 1500 },
  "regulatory-compliance-evidence-platform": { Current: 1 },
  "visual-regression-evaluator": { "Changed pixels (%)": 50 },
  "energy-grid-operations-platform": { "Unserved demand (kWh)": 1.725, "Curtailed generation (kWh)": 1 },
  "financial-risk-settlement-platform": { Exceptions: 1 },
  "semiconductor-yield-timing-platform": { Wafers: 1, "Die records": 3 },
  "public-health-surveillance-platform": { "Suppressed regions": 1 },
  "chemistry-materials-provenance-platform": { Balance: "Conserved" },
  "atmospheric-calibrated-forecast-platform": { "P10–P90 coverage (%)": 50, "Median forecast bias": -2 },
} as const;

for (const [product, metrics] of Object.entries(expected)) {
  test(product + " has an executable schema and analytically correct example", () => {
    const guide = analysisGuide(product)!;
    const report = runAnalysis(product, guide.example, "example");
    for (const [label, value] of Object.entries(metrics)) assert.equal(report.metrics[label], value);
    assert.equal(report.inputSource, "example");
    assert.throws(() => runAnalysis(product, { ...guide.example, fabricatedField: 0 }), /Unrecognized/);
    const spec = workspaceOpenApi({ siteId: product, name: product, stages: ["Review"], origins: [] }, "https://example.test");
    assert.deepEqual(spec.paths["/api/v1/analysis"].post.requestBody.content["application/json"].schema, guide.schema);
  });
}

test("input limits are measured in bytes and unknown IDs fail closed", () => {
  assert.deepEqual(parseInput('\ufeff{"a": 1}'), { a: 1 });
  assert.throws(() => parseInput("abc"), /valid JSON/);
  assert.throws(() => parseInput("é".repeat(MAX_INPUT_BYTES / 2 + 1)), /512 KiB/);
  assert.equal(getAnalysis("constructor"), undefined);
  assert.throws(() => runAnalysis("other", {}), /no standalone analyzer/);
});

test("canary uses percentage points and short samples cannot pass", () => {
  const product = "multicloud-agent-control-plane";
  const baseline = { requests: 100, errors: 5, p95Ms: 200 };
  const input = { baseline, canary: { ...baseline, errors: 6 }, minRequests: 100, maxErrorIncreasePoints: 1, maxLatencyMultiplier: 1.2 };
  assert.equal(runAnalysis(product, input).metrics.Gate, "Pass");
  assert.equal(runAnalysis(product, { ...input, minRequests: 101 }).metrics.Gate, "Insufficient traffic");
  assert.throws(() => runAnalysis(product, { ...input, canary: { ...baseline, errors: 101 } }), /at most/);
});

test("cyclic, ambiguous or missing dependencies are rejected", () => {
  const run = (tasks: unknown) => runAnalysis("multiagent-workflow-engine", { tasks });
  const a = { id: "a", durationMs: 1, dependencies: ["b"] };
  const b = { id: "b", durationMs: 1, dependencies: ["a"] };
  assert.throws(() => run([a]), /unknown dependency/);
  assert.throws(() => run([a,b]), /cycle/);
  assert.throws(() => run([a,a]), /Duplicate/);
});

test("a later rejection supersedes an approval within scope; expiry invalidates a decision", () => {
  const site = "agent-human-approval-ledger";
  const guide = analysisGuide(site)!;
  const first = (guide.example.decisions as Record<string, string>[])[0];
  const reject = { ...first, at: "2026-01-02T10:30:00Z", decision: "reject" };
  assert.equal(runAnalysis(site, { ...guide.example, decisions: [first, reject] }).metrics["Record status"], "Rejected");
  const expired = runAnalysis(site, { ...guide.example, decisions: [first, reject], asOf: "2026-01-02T13:00:00Z" });
  assert.equal(expired.rows?.[0].Decision, "expired");
  assert.throws(() => runAnalysis(site, { ...guide.example, decisions: [first, first] }), /Duplicate/);
  assert.throws(() => runAnalysis(site, { ...guide.example, decisions: [{ ...first, expires: first.at }] }), /expiry/);
  assert.throws(() => runAnalysis(site, { ...guide.example, quorum: 3 }), /Quorum/);
});

test("small cells are censored and impossible case counts fail", () => {
  const site = "public-health-surveillance-platform";
  const report = runAnalysis(site, analysisGuide(site)!.example);
  assert.equal(report.rows?.[1].Cases, null);
  assert.equal(report.rows?.[1]["Cases per 100,000"], null);
  assert.throws(() => runAnalysis(site, { regions: [{ region: "X", cases: 100, population: 40 }] }), /denominator/);
});

test("settlement accounts for missing and unexpected currencies even for zero entries", () => {
  const report = runAnalysis("financial-risk-settlement-platform", {
    expected: [{ transactionId: "T", currency: "USD", minorUnits: 0 }],
    posted: [{ transactionId: "T", currency: "EUR", minorUnits: 0 }],
  });
  assert.deepEqual(report.rows?.map(row => row.Status), ["Missing", "Unexpected"]);
});

test("calibration compares canonical instants and rejects crossings and missing overlap", () => {
  const site = "atmospheric-calibrated-forecast-platform";
  const forecasts = [{ at: "2026-01-01T12:00:00.000Z", p10: 0, p50: 5, p90: 10 }];
  const observations = [{ at: "2026-01-01T12:00:00Z", value: 10 }];
  const input = { unit: "°C", forecasts, observations };
  assert.equal(runAnalysis(site, input).metrics["P10–P90 coverage (%)"], 100);
  assert.throws(() => runAnalysis(site, { ...input, forecasts: [{ ...forecasts[0], p10: 9 }] }), /cross/);
  assert.throws(() => runAnalysis(site, { ...input, observations: [{ ...observations[0], at: "2026-01-01T12:01:00Z" }] }), /No observation/);
});

test("transparent RGB does not change rendered pixels, and dimensions must match", () => {
  const before = Uint8Array.from([255, 0, 0, 0]), after = Uint8Array.from([0, 255, 0, 0]);
  assert.equal(comparePixels(before, after, 1, 1, 0).metrics["Changed pixels"], 0);
  assert.throws(() => comparePixels(before, after, 2, 1, 0), /byte counts/);
});

test("public sources validate identifiers, filter usable rows and keep provenance", async () => {
  const flaky = "flaky-test-forensics", weather = "atmospheric-calibrated-forecast-platform";
  const fixture = { id: 1, workflow_id: 2, head_sha: "a".repeat(40), head_branch: "main", event: "push", conclusion: "failure" };
  const gh = await loadPublicSource(flaky, "actions/checkout", async (url, init) => {
    assert.match(String(url), /^https:\/\/api\.github\.com\/repos\/actions\/checkout\//);
    assert.equal(init?.redirect, "error");
    return Response.json({ workflow_runs: [fixture, { ...fixture, conclusion: "cancelled" }] });
  });
  assert.equal("runs" in gh.data && gh.data.runs?.[0].outcome, "fail");
  const readings = await loadPublicSource(weather, "KJFK", async url => {
    assert.match(String(url), /^https:\/\/api\.weather\.gov\/stations\/KJFK\//);
    return Response.json({ features: [{ properties: {
      timestamp: "2026-01-02T10:00:00+00:00", temperature: { value: 0, unitCode: "wmoUnit:degC" },
    } }] });
  });
  assert.deepEqual(readings.data.observations, [{ at: "2026-01-02T10:00:00.000Z", value: 0 }]);
  await assert.rejects(loadPublicSource(flaky, "owner/.."), /owner\/repository/);
  await assert.rejects(loadPublicSource(weather, "https://example.test"), /station ID/);
  await assert.rejects(loadPublicSource("other", "KJFK"), /no public source/);
  await assert.rejects(loadPublicSource(flaky, "actions/checkout", async () => Response.json({}, { status: 429 })), { status: 429 });
  await assert.rejects(loadPublicSource(flaky, "actions/checkout", async () => Response.json({ workflow_runs: [] })), /no success or failure/);
  await assert.rejects(loadPublicSource(weather, "KJFK", async () => Response.json({ features: [] })), /no|did not return/);
  await assert.rejects(loadPublicSource(weather, "KJFK", async () => new Response("a".repeat(1024 * 1024 + 1))), /exceeds/);
});
