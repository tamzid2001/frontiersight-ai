/** Server-only Firestore workspace persistence. Never import this in client code. */
import { Firestore, type CollectionReference, type DocumentReference } from "@google-cloud/firestore";
import { createHash, createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import { AccessError, requireExpectedVersion, tenantScope, validatePayload, type Principal } from "./policy.ts";

type JsonRecord = Record<string, unknown>;
export type WorkspaceRecord = Readonly<{
  id: string; title: string; stage: number; version: number; payload: JsonRecord;
  createdBy: string; createdAt: string; updatedAt: string;
}>;
export type WorkspaceSummary = Omit<WorkspaceRecord, "payload">;
export type StoragePolicy = Readonly<{ maximumRecords: number; monthlyMutations: number; stages: number }>;

export function firestoreClient(env: NodeJS.ProcessEnv): Firestore {
  const projectId = env.FIRESTORE_PROJECT_ID ?? "";
  const databaseId = env.FIRESTORE_DATABASE_ID ?? "(default)";
  if (!/^[a-z][a-z0-9-]{4,61}[a-z0-9]$/.test(projectId)
      || !/^(\(default\)|[a-z][a-z0-9-]{2,62})$/.test(databaseId)) {
    throw new AccessError(503, "firestore_project_not_configured");
  }
  if (env.FIRESTORE_EMULATOR_HOST) {
    const host = env.FIRESTORE_EMULATOR_HOST;
    const port = Number(host.split(":").at(-1));
    if (env.NODE_ENV === "production" || !projectId.startsWith("demo-")
        || !/^(127\.0\.0\.1|localhost):[0-9]+$/.test(host) || port < 1 || port > 65535) {
      throw new AccessError(503, "unsafe_firestore_emulator_configuration");
    }
    return new Firestore({ projectId, databaseId, host, ssl: false });
  }
  let credentials;
  if (env.FIRESTORE_SERVICE_ACCOUNT_JSON) {
    try {
      const raw = JSON.parse(env.FIRESTORE_SERVICE_ACCOUNT_JSON);
      if (raw.type !== "service_account" || raw.project_id !== projectId
          || typeof raw.client_email !== "string" || !raw.client_email.endsWith(".iam.gserviceaccount.com")
          || typeof raw.private_key !== "string" || !raw.private_key.includes("BEGIN PRIVATE KEY")) {
        throw new Error("invalid credentials");
      }
      credentials = { client_email: raw.client_email, private_key: raw.private_key };
    } catch { throw new AccessError(503, "invalid_firestore_credentials"); }
  }
  if (!credentials && !env.GOOGLE_APPLICATION_CREDENTIALS && env.FIRESTORE_USE_ADC !== "true") {
    throw new AccessError(503, "firestore_credentials_not_configured");
  }
  return new Firestore({ projectId, databaseId, credentials });
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map(key => JSON.stringify(key) + ":" + canonical((value as JsonRecord)[key])).join(",") + "}";
  }
  return JSON.stringify(value);
}
const digest = (value: unknown) => createHash("sha256").update(canonical(value)).digest("hex");

export class FirestoreWorkspace {
  readonly scope: ReturnType<typeof tenantScope>;
  private readonly db: Firestore;
  private readonly policy: StoragePolicy;
  private readonly auditSecret: string;
  private readonly clock: () => Date;
  private readonly root: DocumentReference;
  private readonly records: CollectionReference;
  private readonly audit: CollectionReference;
  private readonly receipts: CollectionReference;
  constructor(db: Firestore, siteId: string, principal: Principal,
              policy: StoragePolicy, auditSecret: string, clock: () => Date = () => new Date()) {
    this.db = db; this.policy = Object.freeze({ ...policy });
    this.auditSecret = auditSecret; this.clock = clock;
    this.scope = tenantScope(siteId, principal);
    if (typeof auditSecret !== "string" || auditSecret.length < 32) throw new AccessError(503, "audit_key_not_configured");
    for (const key of ["maximumRecords", "monthlyMutations", "stages"] as const) {
      const value = policy[key];
      if (!Number.isSafeInteger(value) || value < 1 || value > 1_000_000) {
        throw new AccessError(500, "invalid_storage_policy_" + key);
      }
    }
    if (policy.stages > 32) throw new AccessError(500, "invalid_storage_stage_count");
    const tenant = this.scope.tenantKind === "organization" ? "org_" : "user_";
    this.root = db.collection("quantura_web").doc(siteId).collection("tenants").doc(tenant + this.scope.tenantId);
    this.records = this.root.collection("records");
    this.audit = this.root.collection("audit");
    this.receipts = this.root.collection("idempotency");
  }

  async list(limit = 50, after?: string): Promise<WorkspaceSummary[]> {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw new AccessError(400, "invalid_page_size");
    let query = this.records.orderBy("id").limit(limit)
      .select("id", "title", "stage", "version", "createdBy", "createdAt", "updatedAt");
    if (after !== undefined) {
      if (!/^[a-f0-9-]{36}$/.test(after)) throw new AccessError(400, "invalid_page_cursor");
      query = query.startAfter(after);
    }
    const snapshot = await query.get();
    return snapshot.docs.map(doc => doc.data() as WorkspaceSummary);
  }

  async get(id: string): Promise<WorkspaceRecord> {
    this.validateId(id);
    const record = await this.records.doc(id).get();
    if (!record.exists) throw new AccessError(404, "record_not_found");
    return record.data() as WorkspaceRecord;
  }

  async create(input: { title: string; payload: JsonRecord }, key: string) {
    if (typeof input.title !== "string" || !input.title.trim() || input.title.length > 160) {
      throw new AccessError(400, "title_required");
    }
    validatePayload(input.payload);
    if (Buffer.byteLength(canonical(input.payload)) > 256 * 1024) throw new AccessError(413, "record_payload_too_large");
    return this.mutate("create", randomUUID(), { title: input.title.trim(), payload: input.payload }, key);
  }

  async transition(id: string, expectedVersion: number, stage: number, key: string) {
    this.validateId(id); requireExpectedVersion(expectedVersion);
    if (!Number.isSafeInteger(stage) || stage < 0 || stage >= this.policy.stages) {
      throw new AccessError(400, "invalid_stage");
    }
    return this.mutate("transition", id, { expectedVersion, stage }, key);
  }

  async remove(id: string, expectedVersion: number, key: string) {
    this.validateId(id); requireExpectedVersion(expectedVersion);
    return this.mutate("delete", id, { expectedVersion }, key);
  }

  async auditPage(limit = 50) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw new AccessError(400, "invalid_page_size");
    const rows = await this.audit.orderBy("sequence", "desc").limit(limit).get();
    return rows.docs.map(doc => doc.data());
  }

  /** Verify this bounded latest window against the current head. This detects
   * altered events, not rollback by an administrator controlling the database. */
  async verifiedAuditPage(limit = 50) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw new AccessError(400, "invalid_page_size");
    // One read-only transaction prevents a concurrent append between the event
    // query and head read from appearing to be database tampering.
    const { rows, meta } = await this.db.runTransaction(async tx => {
      const anchor = await tx.get(this.root);
      const snapshot = await tx.get(this.audit.orderBy("sequence", "desc").limit(limit));
      return { rows: snapshot.docs.map(doc => doc.data()), meta: anchor.data() ?? {} };
    }, { readOnly: true });
    let expectedHash = meta.auditHead ?? "genesis";
    let expectedSequence = meta.auditSequence ?? 0;
    for (const row of rows) {
      const { hash, hmac, ...event } = row;
      const signature = createHmac("sha256", this.auditSecret).update(String(hash)).digest("hex");
      if (typeof hmac !== "string" || !/^[a-f0-9]{64}$/.test(hmac)
          || !timingSafeEqual(Buffer.from(signature), Buffer.from(hmac))
          || digest(event) !== hash || hash !== expectedHash || row.sequence !== expectedSequence
          || row.siteId !== this.scope.siteId || row.tenantId !== this.scope.tenantId
          || row.tenantKind !== this.scope.tenantKind) throw new AccessError(503, "audit_integrity_error");
      expectedHash = row.previousHash; expectedSequence--;
    }
    if ((rows.length < limit && (expectedHash !== "genesis" || expectedSequence !== 0))
        || (rows.length === 0 && expectedSequence !== 0)) throw new AccessError(503, "audit_integrity_error");
    return { events: rows, verifiedWindow: true, complete: expectedSequence === 0 };
  }

  /** Durable per-tenant minute budget shared across serverless instances.
   * TTL is housekeeping, not correctness: the window is part of the key. */
  async consumeRequest(maximum: number, channel = "workspace") {
    if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > 1000) {
      throw new AccessError(500, "invalid_request_budget");
    }
    if (!/^[a-z_]{1,24}$/.test(channel)) throw new AccessError(500, "invalid_request_channel");
    const now = this.clock();
    const window = Math.floor(now.getTime() / 60_000);
    const ref = this.root.collection("request_budgets").doc(channel + "_" + window);
    await this.db.runTransaction(async tx => {
      const current = await tx.get(ref);
      const used = current.data()?.used ?? 0;
      if (!Number.isSafeInteger(used) || used < 0) throw new AccessError(503, "invalid_request_budget_state");
      if (used >= maximum) throw new AccessError(429, "request_rate_limit");
      tx.set(ref, { used: used + 1, expiresAt: new Date(now.getTime() + 2 * 86400_000) });
    });
  }

  async usage() {
    const meta = (await this.root.get()).data() ?? {};
    const period = this.clock().toISOString().slice(0, 7);
    return { period, mutations: meta.period === period ? meta.mutations ?? 0 : 0,
      records: meta.recordCount ?? 0, maximumRecords: this.policy.maximumRecords,
      monthlyMutations: this.policy.monthlyMutations };
  }

  private validateId(id: string) {
    if (!/^[a-f0-9-]{36}$/.test(id)) throw new AccessError(400, "invalid_record_id");
  }

  private async mutate(operation: "create" | "transition" | "delete", id: string, body: JsonRecord, key: string) {
    if (typeof key !== "string" || !/^[A-Za-z0-9_-]{16,128}$/.test(key)) throw new AccessError(400, "idempotency_key_required");
    const now = this.clock().toISOString(), period = now.slice(0, 7);
    const actorId = this.scope.actorId;
    // Create IDs are generated once outside the retry callback. Replays bind
    // input, operation AND actor, without depending on a newly generated ID.
    const requestDigest = digest({ operation, actorId, body, target: operation === "create" ? null : id });
    const receipt = this.receipts.doc(digest({ key, actorId }));
    const record = this.records.doc(id);
    return this.db.runTransaction(async transaction => {
      const [anchor, existingReceipt, previous] = await transaction.getAll(this.root, receipt, record);
      if (existingReceipt.exists) {
        const saved = existingReceipt.data()!;
        if (saved.requestDigest !== requestDigest) throw new AccessError(409, "idempotency_key_reused");
        // TTL cleanup is asynchronous. A receipt still present after its
        // declared seven-day window must not silently replay forever.
        if (saved.expiresAt?.toMillis() > Date.parse(now)) return { ...saved.result, replayed: true };
      }
      const meta = anchor.data() ?? {};
      const mutations = meta.period === period ? meta.mutations ?? 0 : 0;
      if (mutations >= this.policy.monthlyMutations) throw new AccessError(429, "monthly_mutation_limit");
      const count = meta.recordCount ?? 0;
      if (![count, mutations, meta.auditSequence ?? 0].every(value => Number.isSafeInteger(value) && value >= 0)) {
        throw new AccessError(503, "invalid_workspace_state");
      }
      if (operation === "create" && previous.exists) throw new AccessError(409, "record_already_exists");
      if (operation !== "create" && !anchor.exists) throw new AccessError(503, "workspace_state_missing");
      if (operation === "create" && count >= this.policy.maximumRecords) throw new AccessError(429, "workspace_record_limit");
      if (operation !== "create" && !previous.exists) throw new AccessError(404, "record_not_found");
      const old = previous.data() as WorkspaceRecord | undefined;
      if (old && old.version !== body.expectedVersion) throw new AccessError(409, "record_version_conflict");
      const next = operation === "create"
        ? { id, title: body.title, payload: body.payload, stage: 0, version: 1, createdBy: actorId, createdAt: now, updatedAt: now }
        : { ...old!, stage: body.stage ?? old!.stage, version: old!.version + 1, updatedAt: now };
      const event = { ...this.scope, operation, recordId: id, version: next.version,
        sequence: (meta.auditSequence ?? 0) + 1, previousHash: meta.auditHead ?? "genesis",
        requestDigest, at: now };
      const hash = digest(event);
      const hmac = createHmac("sha256", this.auditSecret).update(hash).digest("hex");
      const result = operation === "delete" ? { id, deleted: true, version: next.version } : next;
      // All reads above precede every write. No model calls or external side
      // effects occur inside this automatically retried transaction.
      if (operation === "delete") transaction.delete(record);
      else transaction.set(record, next);
      transaction.set(this.root, { period, mutations: mutations + 1,
        recordCount: count + (operation === "create" ? 1 : operation === "delete" ? -1 : 0),
        auditSequence: event.sequence, auditHead: hash, updatedAt: now }, { merge: true });
      transaction.create(this.audit.doc(String(event.sequence).padStart(12, "0")), { ...event, hash, hmac });
      transaction.set(receipt, { requestDigest, result, createdAt: now,
        expiresAt: new Date(Date.parse(now) + 7 * 24 * 3600 * 1000) });
      return { ...result, replayed: false };
    }, { maxAttempts: 5 });
  }
}
