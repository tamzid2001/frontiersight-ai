"""Narrow HTTP adapter for existing scene endpoints in Clerk/Firestore mode."""
from __future__ import annotations

from functools import lru_cache
from datetime import datetime
import os
from urllib.parse import urlparse, parse_qs
import uuid

from services.api.clerk_auth import authenticate, WorkspaceError
from services.api.firestore_scenes import Scenes, client


def enabled():
    return os.environ.get("SCENE_STORE") == "firestore"


@lru_cache(maxsize=1)
def database():
    return client()


def identity(handler):
    return authenticate(handler.headers.get("Authorization", ""))


def handle(handler, route, method):
    """True means this adapter sent a response; legacy SQL is never a fallback."""
    supported = ("/api/scenes", "/api/scenes/update", "/api/scenes/delete", "/api/scene-context")
    if not enabled() or route not in supported:
        return False
    try:
        parties = os.environ.get("CLERK_AUTHORIZED_PARTIES", "").split(",")
        origin = handler.headers.get("Origin")
        if origin and origin not in parties:
            raise WorkspaceError(403, "request_origin_not_allowed")
        actor = identity(handler)
        expected_org = handler.headers.get("X-Workspace-Organization")
        if expected_org is not None and expected_org != (actor.org_id or "personal"):
            raise WorkspaceError(409, "session_workspace_changed")
        if route == "/api/scene-context" and method == "GET":
            handler._send(200, {"userId": actor.user_id, "orgId": actor.org_id,
                "orgRole": actor.org_role, "plan": actor.plan, "storage": "firestore"})
            return True
        store = Scenes(database(), actor, os.environ.get("WORKSPACE_AUDIT_SECRET", ""))
        store.consume_request()
        if route == "/api/scenes" and method == "GET":
            query = parse_qs(urlparse(handler.path).query)
            try:
                limit = int(query.get("limit", ["10"])[0])
            except ValueError:
                raise WorkspaceError(400, "invalid_page_size") from None
            if not 1 <= limit <= 10:
                raise WorkspaceError(400, "invalid_page_size")
            rows = store.list(limit=limit, after=query.get("after", [None])[0])
            scenes = [{"id": row["id"], "name": row["title"], "payload": row["payload"], "version": row["version"],
                "created_at": datetime.fromisoformat(row["updatedAt"]).timestamp(), "shared": bool(actor.org_id)} for row in rows]
            handler._send(200, {"scenes": scenes, "plan": actor.plan, "org": actor.org_id,
                "next": rows[-1]["id"] if len(rows) == limit else None, "storage": "firestore"})
            return True
        if method != "POST":
            raise WorkspaceError(405, "post_required")
        length = int(handler.headers.get("Content-Length", "0"))
        if not 1 <= length <= 300 * 1024:
            raise WorkspaceError(413, "scene_body_budget_exceeded")
        if not handler.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise WorkspaceError(415, "json_required")
        body = handler._body()
        operation = {"/api/scenes": "create", "/api/scenes/update": "update", "/api/scenes/delete": "delete"}.get(route)
        if operation is None:
            raise WorkspaceError(405, "method_not_supported")
        result = store.mutate(operation, body, handler.headers.get("Idempotency-Key", ""))
        handler._send(201 if operation == "create" and not result["replayed"] else 200, {**result, "storage": "firestore"})
    except WorkspaceError as error:
        handler._send(error.status, {"error": error.code, "request_id": str(uuid.uuid4())})
    except (ValueError, TypeError):
        handler._send(400, {"error": "invalid_scene_request", "request_id": str(uuid.uuid4())})
    except Exception:
        handler._send(503, {"error": "workspace_service_unavailable", "request_id": str(uuid.uuid4())})
    return True
