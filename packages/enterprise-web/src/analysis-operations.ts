import { z } from "zod";
import {
  AnalysisError, define, count, id, object, records, probability, utc,
  nonnegative, requireDistinct, rounded, percentile, group, mean, criticalPath,
} from "./analysis-core.ts";

const traffic = object({ requests: count.min(1), errors: count, p95Ms: nonnegative });
const deployment = define("Check a canary rollout",
  "Compare request errors and p95 latency for two deployments using your rollout thresholds.",
  object({ baseline: traffic, canary: traffic, minRequests: count.min(1),
    maxErrorIncreasePoints: z.number().min(0).max(100), maxLatencyMultiplier: z.number().min(1).max(100) }),
  { baseline: { requests: 2000, errors: 10, p95Ms: 180 }, canary: { requests: 1000, errors: 14, p95Ms: 210 },
    minRequests: 500, maxErrorIncreasePoints: 0.5, maxLatencyMultiplier: 1.25 },
  ({ baseline, canary, minRequests, maxErrorIncreasePoints, maxLatencyMultiplier }) => {
    if (baseline.errors > baseline.requests || canary.errors > canary.requests) {
      throw new AnalysisError("Errors must be at most the number of requests.");
    }
    const increase = (canary.errors / canary.requests - baseline.errors / baseline.requests) * 100;
    const delay = canary.p95Ms - baseline.p95Ms;
    const enough = Math.min(baseline.requests, canary.requests) >= minRequests;
    const errorCheck = increase <= maxErrorIncreasePoints + 1e-9;
    const latencyCheck = canary.p95Ms <= baseline.p95Ms * maxLatencyMultiplier;
    return { metrics: { Gate: !enough ? "Insufficient traffic" : errorCheck && latencyCheck ? "Pass" : "Hold",
      "Error increase (percentage points)": rounded(increase), "Allowed error increase (percentage points)": maxErrorIncreasePoints,
      "p95 change (ms)": delay, "Error check": errorCheck ? "Pass" : "Fail", "Latency check": latencyCheck ? "Pass" : "Fail" } };
  });

const scope = { subject: id, tool: id, resource: id };
const permission = define("Audit tool permissions",
  "Review access requests against exact-match or wildcard policies. An explicit deny takes precedence.",
  object({ rules: records(object({ ...scope, effect: z.enum(["allow", "deny"]) })), requests: records(object(scope)) }),
  { rules: [{ subject: "worker", tool: "read", resource: "*", effect: "allow" },
    { subject: "*", tool: "*", resource: "payroll", effect: "deny" }],
  requests: [{ subject: "worker", tool: "read", resource: "inventory" }, { subject: "worker", tool: "read", resource: "payroll" }] },
  ({ rules, requests }) => {
    const indexed = rules.map((rule, index) => ({ ...rule, index: index + 1 }));
    const rows = requests.map(request => {
      const matches = indexed.filter(rule =>
        (["subject", "tool", "resource"] as const).every(field => rule[field] === "*" || rule[field] === request[field]));
      const allowed = matches.length > 0 && matches.every(rule => rule.effect === "allow");
      return { Subject: request.subject, Tool: request.tool, Resource: request.resource,
        Decision: allowed ? "Allow" : "Deny", "Matching rule numbers": matches.map(rule => rule.index).join(", ") || null };
    });
    return { metrics: { Requests: rows.length, Denied: rows.filter(row => row.Decision === "Deny").length }, rows };
  });

const observability = define("Measure tool latency and usage",
  "Aggregate tool calls by name and calculate nearest-rank latency, error rates and estimated token costs.",
  object({ costPerMillionTokens: nonnegative, calls: records(object({ tool: id, ms: nonnegative, error: z.boolean(), tokens: count })) }),
  { costPerMillionTokens: 0.6, calls: [{ tool: "lookup", ms: 12, error: false, tokens: 500 },
    { tool: "lookup", ms: 100, error: true, tokens: 250 }] },
  ({ costPerMillionTokens, calls }) => ({
    metrics: { Calls: calls.length, "p95 latency (ms)": percentile(calls.map(call => call.ms), 0.95) },
    rows: Array.from(group(calls, row => row.tool), ([tool, rows]) => {
      const tokens = rows.reduce((sum, row) => sum + row.tokens, 0);
      return { Tool: tool, Calls: rows.length, "Error rate (%)": rounded(100 * rows.filter(r => r.error).length / rows.length),
        "p50 (ms)": percentile(rows.map(r => r.ms), 0.5), "p95 (ms)": percentile(rows.map(r => r.ms), 0.95),
        Tokens: tokens, "Estimated cost (USD)": rounded(tokens * costPerMillionTokens / 1e6) };
    }),
  }));

const digest = z.string().regex(/^[a-f0-9]{64}$/i).transform(value => value.toLowerCase());
const approval = define("Reconcile an approval record",
  "Check distinct reviewer decisions for a specific operation digest as of a supplied UTC timestamp.",
  object({ operation: id, digest, asOf: utc, quorum: count.min(1), reviewers: records(id),
    decisions: records(object({ reviewer: id, operation: id, digest, at: utc, expires: utc,
      decision: z.enum(["approve", "reject"]) })) }),
  { operation: "export-32", digest: "a".repeat(64), asOf: "2026-01-02T11:00:00Z",
    quorum: 2, reviewers: ["operator-a", "operator-b"], decisions: [
      { reviewer: "operator-a", operation: "export-32", digest: "a".repeat(64),
        at: "2026-01-02T10:00:00Z", expires: "2026-01-02T12:00:00Z", decision: "approve" }] },
  ({ operation, digest: expected, asOf, quorum, reviewers, decisions }) => {
    requireDistinct(reviewers, "reviewer");
    if (quorum > reviewers.length) throw new AnalysisError("Quorum exceeds the number of eligible reviewers.");
    const cutoff = Date.parse(asOf);
    const matching = decisions.filter(row => row.operation === operation && row.digest === expected &&
      reviewers.includes(row.reviewer) && Date.parse(row.at) <= cutoff);
    requireDistinct(matching.map(row => JSON.stringify([row.reviewer, Date.parse(row.at)])), "reviewer decision timestamp");
    for (const row of matching) {
      if (Date.parse(row.expires) <= Date.parse(row.at)) throw new AnalysisError("Decision expiry must follow its creation time.");
    }
    const rows = Array.from(group(matching, row => row.reviewer), ([reviewer, items]) => {
      const latest = items.reduce((a, b) => Date.parse(a.at) > Date.parse(b.at) ? a : b);
      return { Reviewer: reviewer, Decision: Date.parse(latest.expires) <= cutoff ? "expired" : latest.decision, AsOf: asOf };
    });
    const approvals = rows.filter(row => row.Decision === "approve").length;
    const veto = rows.some(row => row.Decision === "reject");
    return { metrics: { "Record status": veto ? "Rejected" : approvals >= quorum ? "Quorum recorded" : "Insufficient approvals",
      Approvals: approvals, Quorum: quorum, "Evidence type": "Submitted records" }, rows };
  });

const graph = records(object({ id, durationMs: nonnegative, dependencies: z.array(id).max(100) }));
const graphExample = [
  { id: "retrieve", durationMs: 90, dependencies: [] },
  { id: "parse", durationMs: 30, dependencies: ["retrieve"] },
  { id: "score", durationMs: 60, dependencies: ["retrieve"] },
  { id: "report", durationMs: 10, dependencies: ["parse", "score"] },
];
const workflow = define("Find a workflow’s critical path",
  "Validate a dependency graph and compute the earliest finish times assuming independent work can run in parallel.",
  object({ tasks: graph }), { tasks: graphExample }, ({ tasks }) => criticalPath(tasks));
const distributed = define("Find a trace’s critical dependency path",
  "Use measured span durations and declared dependencies to locate the longest serial chain.",
  object({ spans: graph }), { spans: graphExample }, ({ spans }) => criticalPath(spans));

const classifier = define("Score binary predictions",
  "Compare probabilities with known outcomes. Inspect threshold metrics, Brier score and log loss.",
  object({ threshold: probability, predictions: records(object({ probability, outcome: z.union([z.literal(0), z.literal(1)]) })) }),
  { threshold: 0.5, predictions: [{ probability: 0.8, outcome: 1 }, { probability: 0.3, outcome: 0 },
    { probability: 0.7, outcome: 0 }] },
  ({ threshold, predictions }) => {
    let tp = 0, fp = 0, tn = 0, fn = 0;
    const scores = predictions.map(({ probability: p, outcome }) => {
      if (p >= threshold) { if (outcome) tp++; else fp++; }
      else { if (outcome) fn++; else tn++; }
      return { error: (p - outcome) ** 2, loss: -Math.log(Math.max(1e-15, outcome ? p : 1 - p)) };
    });
    return { metrics: { Predictions: predictions.length, "True positives": tp, "False positives": fp,
      "True negatives": tn, "False negatives": fn, Accuracy: rounded((tp + tn) / predictions.length),
      Precision: tp + fp ? rounded(tp / (tp + fp)) : null, Recall: tp + fn ? rounded(tp / (tp + fn)) : null,
      F1: 2 * tp + fp + fn ? rounded(2 * tp / (2 * tp + fp + fn)) : null,
      "Brier score": rounded(mean(scores.map(s => s.error))), "Log loss (natural log)": rounded(mean(scores.map(s => s.loss))) } };
  });

const run = object({ runId: id, check: id, revision: id, context: id, outcome: z.enum(["pass", "fail"]) });
const flaky = define("Find repeated run instability",
  "Compare outcomes only within the same check, revision and execution context. Mixed runs identify candidates for investigation.",
  object({ runs: records(run) }),
  { runs: [{ runId: "1", check: "Unit tests", revision: "abc", context: "Ubuntu 24", outcome: "pass" },
    { runId: "2", check: "Unit tests", revision: "abc", context: "Ubuntu 24", outcome: "fail" }] },
  ({ runs }) => {
    const rows = Array.from(group(runs, row => JSON.stringify([row.check, row.revision, row.context])), ([, values]) => {
      requireDistinct(values.map(value => value.runId), "run ID within a group");
      const fails = values.filter(row => row.outcome === "fail").length;
      return { Check: values[0].check, Revision: values[0].revision, Context: values[0].context,
        Passed: values.length - fails, Failed: fails, "Mixed outcomes": fails > 0 && fails < values.length ? "Yes" : "No" };
    });
    return { metrics: { Runs: runs.length, Groups: rows.length, "Mixed groups": rows.filter(row => row["Mixed outcomes"] === "Yes").length }, rows };
  });

const incident = define("Reconstruct an incident timeline",
  "Calculate time from impact to detection and recovery using timestamped incident events.",
  object({ events: records(object({ at: utc, kind: z.enum(["impact", "detected", "mitigated", "recovered", "note"]), description: id })) }),
  { events: [{ at: "2026-01-02T10:00:00Z", kind: "impact", description: "Requests failed" },
    { at: "2026-01-02T10:04:00Z", kind: "detected", description: "Alert fired" },
    { at: "2026-01-02T10:25:00Z", kind: "recovered", description: "Service restored" }] },
  ({ events }) => {
    const ordered = events.slice().sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
    const stages = ordered.filter(event => event.kind !== "note");
    const order = ["impact", "detected", "mitigated", "recovered"];
    if (stages.some((event, index) => index && order.indexOf(event.kind) <= order.indexOf(stages[index - 1].kind))) {
      throw new AnalysisError("Incident stages must be unique and follow impact, detected, mitigated, recovered order.");
    }
    const impact = stages.find(event => event.kind === "impact");
    const elapsed = (kind: string) => {
      const target = stages.find(event => event.kind === kind);
      return target && impact ? (Date.parse(target.at) - Date.parse(impact.at)) / 1000 : null;
    };
    return { metrics: { Events: events.length, "Detection (seconds)": elapsed("detected"),
      "Mitigation (seconds)": elapsed("mitigated"), "Recovery (seconds)": elapsed("recovered") },
    rows: ordered.map(event => ({ "Timestamp (UTC)": event.at, Stage: event.kind, Description: event.description })) };
  });

const compliance = define("Check evidence coverage",
  "Match supplied artifact records to your checklist and flag missing, duplicate or expired evidence.",
  object({ asOf: utc, required: records(id),
    artifacts: z.array(object({ requirement: id, sha256: digest, expiresAt: utc })).max(2000) }),
  { asOf: "2026-01-02T00:00:00Z", required: ["retention-policy", "access-review"],
    artifacts: [{ requirement: "retention-policy", sha256: "b".repeat(64), expiresAt: "2026-02-01T00:00:00Z" }] },
  ({ asOf, required, artifacts }) => {
    requireDistinct(required, "checklist requirement");
    const groups = group(artifacts, row => row.requirement);
    const rows = required.map(requirement => {
      const matches = groups.get(requirement) ?? [];
      const usable = matches.filter(record => Date.parse(record.expiresAt) > Date.parse(asOf));
      return { Requirement: requirement, Status: matches.length > 1 ? "Multiple records" : usable.length ? "Current" :
        matches.length ? "Expired" : "Missing", "Artifact records": matches.length };
    });
    return { metrics: { Requirements: required.length, Current: rows.filter(r => r.Status === "Current").length,
      "Unlisted artifacts": artifacts.filter(item => !required.includes(item.requirement)).length }, rows };
  });

export const operations = {
  "multicloud-agent-control-plane": deployment, "agent-tool-permission-firewall": permission,
  "mcp-tool-observability-hub": observability, "agent-human-approval-ledger": approval,
  "multiagent-workflow-engine": workflow, "distributed-debugging-bench": distributed,
  "agent-evaluation-orchestrator": classifier, "flaky-test-forensics": flaky,
  "production-incident-replay-lab": incident, "regulatory-compliance-evidence-platform": compliance,
};
