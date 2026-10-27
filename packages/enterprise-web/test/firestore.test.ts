import { after, test } from "node:test";
import assert from "node:assert/strict";
import { randomBytes, randomUUID } from "node:crypto";
import { firestoreClient, FirestoreWorkspace } from "../src/firestore.ts";
import type { Principal } from "../src/policy.ts";

const emulator = process.env.FIRESTORE_EMULATOR_HOST;
const actor: Principal = { userId: "user_alice", orgId: "org_acme", orgRole: "org:admin", features: ["api_access", "export"] };
const policy = { maximumRecords: 10, monthlyMutations: 30, stages: 4 };
const secret = randomBytes(32).toString("hex");
const key = () => randomUUID();
const db = emulator ? firestoreClient({ FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_EMULATOR_HOST: emulator }) : null;
after(async () => { if (db) await db.terminate(); });

function workspace(options: { principal?: Principal; limit?: number; mutations?: number; clock?: () => Date } = {}) {
  const site = "unit-" + randomBytes(6).toString("hex");
  return new FirestoreWorkspace(db!, site, options.principal ?? actor,
    { ...policy, maximumRecords: options.limit ?? 10, monthlyMutations: options.mutations ?? 30 }, secret, options.clock);
}

test("Firestore must have an explicit project and safe emulator/credential settings", async () => {
  for (const env of [{}, { FIRESTORE_PROJECT_ID: "real-quantura" },
    { FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_EMULATOR_HOST: "evil.example:80" },
    { FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_EMULATOR_HOST: "localhost:99", NODE_ENV: "production" },
    { FIRESTORE_PROJECT_ID: "real-quantura", FIRESTORE_EMULATOR_HOST: "localhost:99" },
    { FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_SERVICE_ACCOUNT_JSON: "not json" },
    { FIRESTORE_PROJECT_ID: "demo-quantura-web", FIRESTORE_SERVICE_ACCOUNT_JSON: JSON.stringify({ type: "service_account", project_id: "other-project" }) }]) {
    assert.throws(() => firestoreClient(env), { status: 503 });
  }
});

test("actual emulator roundtrip, bounded projections and optimistic transitions", { skip: !emulator }, async () => {
  const store = workspace();
  const created = await store.create({ title: "Calibrate wafer", payload: { readings: [1, 2] } }, key());
  assert.equal(created.version, 1); assert.equal(created.replayed, false);
  assert.deepEqual((await store.get(created.id as string)).payload, { readings: [1, 2] });
  const page = await store.list(1);
  assert.equal(page[0].title, "Calibrate wafer"); assert.equal("payload" in page[0], false);
  const changed = await store.transition(created.id as string, 1, 2, key());
  assert.equal(changed.version, 2); assert.equal(changed.stage, 2);
  await assert.rejects(store.transition(created.id as string, 1, 3, key()), { code: "record_version_conflict" });
  const audit = await store.auditPage();
  assert.equal(audit.length, 2); assert.equal(audit[0].previousHash, audit[1].hash);
  assert.match(audit[0].hmac, /^[a-f0-9]{64}$/);
});

test("idempotency replays once, binds arguments and never consumes the quota twice", { skip: !emulator }, async () => {
  const store = workspace(), idempotency = key();
  const input = { title: "Safety review", payload: { approved: false } };
  const first = await store.create(input, idempotency), second = await store.create(input, idempotency);
  assert.equal(second.id, first.id); assert.equal(second.replayed, true);
  assert.equal((await store.usage()).mutations, 1);
  assert.equal((await store.list()).length, 1);
  await assert.rejects(store.create({ ...input, payload: { approved: true } }, idempotency), { code: "idempotency_key_reused" });
});

test("tenant and product namespaces cannot read or mutate each other's records", { skip: !emulator }, async () => {
  const site = "unit-" + randomBytes(6).toString("hex");
  const a = new FirestoreWorkspace(db!, site, actor, policy, secret);
  const b = new FirestoreWorkspace(db!, site, { ...actor, orgId: "org_other" }, policy, secret);
  const personal = new FirestoreWorkspace(db!, site, { ...actor, orgId: null }, policy, secret);
  const otherProduct = new FirestoreWorkspace(db!, site + "-other", actor, policy, secret);
  const created = await a.create({ title: "Private organizational data", payload: {} }, key());
  for (const store of [b, personal, otherProduct]) {
    assert.deepEqual(await store.list(), []);
    await assert.rejects(store.get(created.id as string), { code: "record_not_found" });
    // An absent tenant anchor also fails closed rather than resurrecting state.
    await assert.rejects(store.transition(created.id as string, 1, 1, key()), { status: 503 });
  }
});

test("concurrent edits have exactly one winner and one audit change", { skip: !emulator }, async () => {
  const store = workspace();
  const row = await store.create({ title: "Concurrent review", payload: {} }, key());
  const results = await Promise.allSettled([store.transition(row.id as string, 1, 1, key()), store.transition(row.id as string, 1, 2, key())]);
  assert.equal(results.filter(x => x.status === "fulfilled").length, 1);
  const failure = results.find(x => x.status === "rejected") as PromiseRejectedResult;
  assert.equal(failure.reason.code, "record_version_conflict");
  assert.equal((await store.auditPage()).length, 2);
});

test("record limits, monthly quotas, delete and month rollover are transactional", { skip: !emulator }, async () => {
  let now = new Date("2026-10-27T12:00:00Z");
  const store = workspace({ limit: 1, mutations: 2, clock: () => now });
  const row = await store.create({ title: "One slot", payload: {} }, key());
  await assert.rejects(store.create({ title: "Too many", payload: {} }, key()), { code: "workspace_record_limit" });
  const removed = await store.remove(row.id as string, 1, key()); assert.equal(removed.deleted, true);
  assert.equal((await store.usage()).records, 0);
  await assert.rejects(store.create({ title: "Too many writes", payload: {} }, key()), { code: "monthly_mutation_limit" });
  now = new Date("2026-11-01T00:00:00Z");
  await store.create({ title: "New billing month", payload: {} }, key());
  assert.equal((await store.usage()).mutations, 1);
});

test("validation precedes writes and storage responses remain bounded", { skip: !emulator }, async () => {
  const store = workspace();
  for (const title of ["", "x".repeat(161)]) await assert.rejects(store.create({ title, payload: {} }, key()), { status: 400 });
  await assert.rejects(store.create({ title: "Large", payload: { text: "x".repeat(300_000) } }, key()), { status: 413 });
  await assert.rejects(store.create({ title: "Key", payload: {} }, "short"), { code: "idempotency_key_required" });
  await assert.rejects(store.list(101), { code: "invalid_page_size" });
  await assert.rejects(store.list(1, "../other-tenant"), { code: "invalid_page_cursor" });
  await assert.rejects(store.get("../other-tenant"), { code: "invalid_record_id" });
  await assert.rejects(store.auditPage(1000), { code: "invalid_page_size" });
  await assert.rejects(store.transition(key(), 0, 1, key()), { code: "expected_version_required" });
  await assert.rejects(store.transition(key(), 1, 99, key()), { code: "invalid_stage" });
  assert.deepEqual(await store.list(), []);
});

test("direct unauthenticated Firestore clients cannot read server-owned data", { skip: !emulator }, async () => {
  const response = await fetch("http://" + emulator + "/v1/projects/demo-quantura-web/databases/(default)/documents/quantura_web/test");
  assert.equal(response.status, 403);
});
