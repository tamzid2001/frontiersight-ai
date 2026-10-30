"""Durable, namespace-scoped scene storage; server SDK, no client Firestore access.

The emulator validates application behavior, not production indexes or contention.
Audit signatures detect modified events; privileged database rollback is not proven.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import math
import os
import re
import uuid
from threading import Lock
from contextlib import contextmanager

_LOCAL_LOCKS = tuple(Lock() for _ in range(64))


@contextmanager
def _local_guard(path, timeout=2):
    """Bound same-process contention; Firestore remains the cross-process authority."""
    lock = _LOCAL_LOCKS[int(hashlib.sha256(path.encode()).hexdigest()[:8],16) % len(_LOCAL_LOCKS)]
    if not lock.acquire(timeout=timeout):
        raise WorkspaceError(429, "workspace_busy_retry_same_request")
    try:
        yield
    finally:
        lock.release()


def _transaction_error(error):
    from google.api_core.exceptions import Aborted
    if isinstance(error.__cause__, Aborted):
        raise WorkspaceError(503, "transaction_contention_retry_same_request") from None
    raise error

from services.api.clerk_auth import Identity, WorkspaceError


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def decode_row(row):
    if 'payloadJson' in row:
        row = {**row, 'payload': json.loads(row['payloadJson'])}
        row.pop('payloadJson')
    return row


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise WorkspaceError(400, "scene_object_required")
    pending, count = [(payload, 0)], 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 8 or count > 10000:
            raise WorkspaceError(400, "payload_budget_exceeded")
        if isinstance(value, dict):
            if any(not isinstance(key, str) or key in ("__proto__", "constructor", "prototype") for key in value):
                raise WorkspaceError(400, "invalid_payload_key")
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise WorkspaceError(400, "nonfinite_payload")
        elif value is not None and not isinstance(value, (str, bool, int, float)):
            raise WorkspaceError(400, "json_value_required")
    if len(_canonical(payload).encode()) > 256 * 1024:
        raise WorkspaceError(413, "scene_payload_too_large")


def client(env=None):
    env = os.environ if env is None else env
    project = env.get("FIRESTORE_PROJECT_ID", "")
    database = env.get("FIRESTORE_DATABASE_ID", "(default)")
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project) or not re.fullmatch(r"\(default\)|[a-z][a-z0-9-]{2,62}", database):
        raise WorkspaceError(503, "firestore_not_configured")
    from google.cloud import firestore
    emulator = env.get("FIRESTORE_EMULATOR_HOST")
    if emulator:
        if (env.get("VERCEL_ENV") == "production" or not project.startswith("demo-")
            or not re.fullmatch(r"(localhost|127\.0\.0\.1):[0-9]{1,5}", emulator)
            or not 1 <= int(emulator.rsplit(":", 1)[1]) <= 65535):
            raise WorkspaceError(503, "unsafe_firestore_emulator")
        # The SDK reads this process variable. Do not pretend a supplied custom
        # mapping redirects its transport; require it to match explicitly.
        if os.environ.get("FIRESTORE_EMULATOR_HOST") != emulator:
            raise WorkspaceError(503, "emulator_environment_mismatch")
        from google.auth.credentials import AnonymousCredentials
        return firestore.Client(project=project, database=database, credentials=AnonymousCredentials())
    credentials = None
    if env.get("FIRESTORE_SERVICE_ACCOUNT_JSON"):
        try:
            raw = json.loads(env["FIRESTORE_SERVICE_ACCOUNT_JSON"])
            if raw.get("project_id") != project or raw.get("type") != "service_account":
                raise ValueError("wrong project")
            from google.oauth2.service_account import Credentials
            credentials = Credentials.from_service_account_info(raw)
        except Exception:
            raise WorkspaceError(503, "invalid_firestore_credentials") from None
    if credentials is None and not env.get("GOOGLE_APPLICATION_CREDENTIALS") and env.get("FIRESTORE_USE_ADC") != "true":
        raise WorkspaceError(503, "firestore_credentials_not_configured")
    return firestore.Client(project=project, database=database, credentials=credentials)


class Scenes:
    def __init__(self, database, identity: Identity, secret: str, *, clock=None, resource="scenes"):
        if not isinstance(identity, Identity):
            raise WorkspaceError(401, "verified_identity_required")
        if len(secret) < 32:
            raise WorkspaceError(503, "audit_key_not_configured")
        self.db, self.identity, self.secret = database, identity, secret
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.root = database.collection("quantura_web").document("frontiersight-ai").collection("tenants").document(identity.tenant)
        if resource not in ("scenes", "objects", "media"):
            raise WorkspaceError(400, "unsupported_resource")
        if resource != "scenes":
            self.root = self.root.collection("libraries").document(resource)
        self.records = self.root.collection("records")
        self.maximum, self.mutations = ((12 if resource == "objects" else 25 if resource == "media" else 10), 100) if identity.plan == "explorer" else (5000, 20000)

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9-]{36}", value):
            raise WorkspaceError(400, "invalid_scene_id")

    def list(self, limit=25, after=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WorkspaceError(400, "invalid_page_size")
        query = self.records.order_by("id").limit(limit)
        if after:
            self._id(after)
            query = query.start_after({"id": after})
        return [decode_row(row.to_dict()) for row in query.stream(timeout=10)]

    def get(self, record_id):
        self._id(record_id)
        row = self.records.document(record_id).get(timeout=10)
        if not row.exists:
            raise WorkspaceError(404, "record_not_found")
        return decode_row(row.to_dict())

    def consume_request(self, maximum=None):
        maximum = maximum or (60 if self.identity.plan == "explorer" else 300)
        now = self.clock()
        ref = self.root.collection("request_budgets").document("workspace_" + str(int(now.timestamp() // 60)))
        from google.cloud import firestore
        @firestore.transactional
        def consume(tx):
            count = (ref.get(transaction=tx).to_dict() or {}).get("used", 0)
            if type(count) is not int or count < 0:
                raise WorkspaceError(503, "invalid_request_budget_state")
            if count >= maximum:
                raise WorkspaceError(429, "request_rate_limit")
            tx.set(ref, {"used": count + 1, "expiresAt": now + timedelta(days=2)})
        with _local_guard(self.root.path):
            try: consume(self.db.transaction(max_attempts=5))
            except ValueError as error: _transaction_error(error)

    def mutate(self, operation, body, key):
        if operation not in ("create", "update", "delete") or not isinstance(body, dict):
            raise WorkspaceError(400, "invalid_scene_operation")
        allowed = {"name", "payload"} if operation == "create" else {"id", "name", "payload", "expectedVersion"} if operation == "update" else {"id", "expectedVersion"}
        if set(body) - allowed:
            raise WorkspaceError(400, "unexpected_request_field")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise WorkspaceError(400, "idempotency_key_required")
        if operation == "delete" and not self.identity.administrator:
            raise WorkspaceError(403, "organization_admin_required")
        if operation != "delete":
            name = body.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 120:
                raise WorkspaceError(400, "scene_name_required")
            validate_payload(body.get("payload"))
        if operation != "create":
            self._id(body.get("id"))
            if type(body.get("expectedVersion")) is not int or body["expectedVersion"] < 1:
                raise WorkspaceError(400, "expected_version_required")
        record_id = str(uuid.uuid4()) if operation == "create" else body["id"]
        ref = self.records.document(record_id)
        now = self.clock()
        period, timestamp = now.strftime("%Y-%m"), now.isoformat()
        request_digest = _digest({"operation": operation, "actor": self.identity.user_id, "body": body})
        receipt = self.root.collection("idempotency").document(_digest([self.identity.user_id, key]))
        from google.cloud import firestore

        @firestore.transactional
        def apply(transaction):
            anchor, saved, prior = (item.get(transaction=transaction) for item in (self.root, receipt, ref))
            if saved.exists:
                data = saved.to_dict()
                if data["requestDigest"] != request_digest:
                    raise WorkspaceError(409, "idempotency_key_reused")
                if data["expiresAt"] > now:
                    return {**data["result"], "replayed": True}
            meta = anchor.to_dict() or {}
            count = meta.get("recordCount", 0)
            used = meta.get("mutations", 0) if meta.get("period") == period else 0
            sequence = meta.get("auditSequence", 0)
            if any(type(n) is not int or n < 0 for n in (count, used, sequence)):
                raise WorkspaceError(503, "invalid_workspace_state")
            if used >= self.mutations:
                raise WorkspaceError(429, "monthly_mutation_limit")
            if operation == "create" and count >= self.maximum:
                raise WorkspaceError(429, "workspace_record_limit")
            if operation != "create" and not prior.exists:
                raise WorkspaceError(404, "scene_not_found")
            old = decode_row(prior.to_dict() or {})
            if operation != "create" and old["version"] != body["expectedVersion"]:
                raise WorkspaceError(409, "scene_version_conflict")
            row = {"id": record_id, "title": body.get("name", old.get("title")),
                   "payload": body.get("payload", old.get("payload")), "stage": 0,
                   "version": old.get("version", 0) + 1, "createdBy": old.get("createdBy", self.identity.user_id),
                   "createdAt": old.get("createdAt", timestamp), "updatedAt": timestamp}
            event = {"operation": operation, "recordId": record_id, "actorId": self.identity.user_id,
                     "tenantId": self.identity.tenant, "siteId": "frontiersight-ai", "version": row["version"],
                     "sequence": sequence + 1, "previousHash": meta.get("auditHead", "genesis"),
                     "requestDigest": request_digest, "at": timestamp}
            digest = _digest(event)
            event.update(hash=digest, hmac=hmac.new(self.secret.encode(), digest.encode(), hashlib.sha256).hexdigest())
            result = {"id": record_id, "version": row["version"], "deleted": operation == "delete"}
            # No external effects occur in this retried transaction. All reads precede writes.
            if operation == "delete":
                transaction.delete(ref)
            else:
                # Firestore forbids arrays directly containing arrays. Preserve
                # exact JSON geometry (including waypoint matrices) as a bounded
                # canonical string instead of lossy flattening or coordinate maps.
                encoded = dict(row)
                encoded['payloadJson'] = _canonical(encoded.pop('payload'))
                transaction.set(ref, encoded)
            transaction.set(self.root, {"period": period, "mutations": used + 1,
                "recordCount": count + (1 if operation == "create" else -1 if operation == "delete" else 0),
                "auditSequence": sequence + 1, "auditHead": digest}, merge=True)
            transaction.create(self.root.collection("audit").document(f"{sequence+1:012}"), event)
            transaction.set(receipt, {"requestDigest": request_digest, "result": result,
                "expiresAt": now + timedelta(days=7), "createdAt": timestamp})
            return {**result, "replayed": False}

        with _local_guard(self.root.path):
            try: return apply(self.db.transaction(max_attempts=5))
            except ValueError as error: _transaction_error(error)
