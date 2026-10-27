import hashlib, hmac, json, os, threading, time, urllib.request, urllib.error
import pytest

@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("BYOK_ENCRYPTION_KEY", raising=False)
    from services.api import store
    store._conn = None
    from http.server import ThreadingHTTPServer
    from services.api.server import H
    srv = ThreadingHTTPServer(("127.0.0.1", 8807), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:8807"
    srv.shutdown(); store._conn = None

def call(base, path, payload=None, token=None, method="POST", raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method,
        headers={"Content-Type": "application/json", **(headers or {}),
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

def signup(base, email="ada@example.com"):
    s, out = call(base, "/api/auth/signup", {"name": "Ada Lovelace", "email": email, "password": "correct-horse-9"})
    assert s == 201, out
    return out["token"]

def test_signup_login_me_and_session(api):
    token = signup(api)
    s, me = call(api, "/api/me", method="GET", token=token)
    assert s == 200 and me["authenticated"] and me["plan"] == "explorer"
    s, out = call(api, "/api/auth/login", {"email": "ada@example.com", "password": "wrong-password"})
    assert s == 401
    s, out = call(api, "/api/auth/signup", {"name": "Ada Lovelace", "email": "ada@example.com", "password": "correct-horse-9"})
    assert s == 409

def test_scenes_quota_and_auth(api):
    s, out = call(api, "/api/scenes", {"name": "x", "payload": {"objects": []}})
    assert s == 401
    token = signup(api)
    for i in range(10):
        s, out = call(api, "/api/scenes", {"name": f"s{i}", "payload": {"objects": []}}, token)
        assert s == 201, out
    s, out = call(api, "/api/scenes", {"name": "one-too-many", "payload": {"objects": []}}, token)
    assert s == 402 and out["capability"].startswith("server_scenes") and out["upgrade_url"]
    s, out = call(api, "/api/scenes", method="GET", token=token)
    assert len(out["scenes"]) == 10

def test_byok_gate_and_roundtrip(api, monkeypatch):
    token = signup(api)
    s, out = call(api, "/api/keys/meta", {"key": "sk-test-1234567890"}, token)
    assert s == 402  # BYOK is a Researcher entitlement; explorer is gated
    # grant researcher by direct subscription row (webhook path tested separately)
    from services.api import store
    uid = store.one("SELECT id FROM users WHERE email='ada@example.com'")["id"]
    store.q("INSERT OR REPLACE INTO subscriptions(user_id, price_id, status, updated_at) VALUES(?,?,?,?)",
            (uid, "price_test", "active", time.time()))
    monkeypatch.setenv("BYOK_ENCRYPTION_KEY", "test-byok-secret")
    s, out = call(api, "/api/keys/meta", {"key": "sk-test-1234567890"}, token)
    assert s == 200 and out["last4"] == "7890"
    s, me = call(api, "/api/me", method="GET", token=token)
    assert me["plan"] == "researcher" and me["meta_key"]["configured"] and me["meta_key"]["last4"] == "7890"

def test_checkout_honest_when_unconfigured(api):
    token = signup(api)
    s, out = call(api, "/api/billing/checkout", {"period": "monthly"}, token)
    assert s == 503 and out["code"] == "BILLING_NOT_CONFIGURED"

def test_webhook_signature_and_idempotency(api, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    signup(api)
    from services.api import store
    uid = store.one("SELECT id FROM users WHERE email='ada@example.com'")["id"]
    event = {"id": "evt_test_1", "type": "customer.subscription.created",
             "data": {"object": {"id": "sub_1", "customer": "cus_1", "status": "active",
                                  "current_period_end": 9999999999, "cancel_at_period_end": False,
                                  "metadata": {"user_id": str(uid)},
                                  "items": {"data": [{"price": {"id": "price_test"}}]}}}}
    raw = json.dumps(event).encode()
    ts = str(int(time.time()))
    sig = hmac.new(b"whsec_test_123", f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    s, out = call(api, "/api/billing/webhook", raw=raw, headers={"Stripe-Signature": f"t={ts},v1={sig}"})
    assert s == 200, out
    s, out = call(api, "/api/billing/webhook", raw=raw, headers={"Stripe-Signature": f"t={ts},v1={sig}"})
    assert out.get("duplicate") is True
    s, me = call(api, "/api/me", method="GET", token=None)  # no token: guest view
    token = None
    s2, login = call(api, "/api/auth/login", {"email": "ada@example.com", "password": "correct-horse-9"})
    s, me = call(api, "/api/me", method="GET", token=login["token"])
    assert me["plan"] == "researcher"
    # forged signature rejected
    s, out = call(api, "/api/billing/webhook", raw=raw, headers={"Stripe-Signature": f"t={ts},v1=deadbeef"})
    assert s == 400

def test_mc_quota_gate(api):
    payload = {"scenario": "warehouse-near-miss", "mc_runs": 5000}
    s, out = call(api, "/api/counterfactual", payload)
    assert s == 402 and "mc_runs" in out["capability"]

def test_waitlist_and_quote(api):
    s, out = call(api, "/api/waitlist", {"email": "a@b.co", "plan": "Researcher"})
    assert s == 201
    s, out = call(api, "/api/sales/quote", {"company": "Acme", "email": "ops@acme.co", "seats": "12", "needs": "SSO"})
    assert s == 201
    s, out = call(api, "/api/sales/quote", {"company": "", "email": ""})
    assert s == 400


def test_support_and_org_provisioning(api, tmp_path):
    token = signup(api, "ops@acme.example")
    s, out = call(api, "/api/support", {"subject": "SAM question", "message": "How do video quotas work?"}, token)
    assert s == 201 and out["priority"] is False  # explorer = standard queue
    s, out = call(api, "/api/org", method="GET", token=token)
    assert out["org"] is None
    # provision via the same code path as scripts/provision_org.py
    from services.api import store
    import time as _t
    uid = store.one("SELECT id FROM users WHERE email='ops@acme.example'")["id"]
    store.q("INSERT OR REPLACE INTO org_members(user_id, org, role, created_at) VALUES(?,?,?,?)",
            (uid, "Acme Safety", "owner", _t.time()))
    store.audit(uid, "org_provisioned", "Acme Safety (owner)", org="Acme Safety")
    s, out = call(api, "/api/auth/login", {"email": "ops@acme.example", "password": "correct-horse-9"})
    token2 = out["token"]
    s, out = call(api, "/api/org", method="GET", token=token2)
    assert out["org"] == "Acme Safety" and out["role"] == "owner" and len(out["members"]) == 1
    s, me = call(api, "/api/me", method="GET", token=token2)
    assert me["plan"] == "team"
    # org-shared scene visible to a second member
    s, out = call(api, "/api/scenes", {"name": "shared-cell", "payload": {"objects": []}}, token2)
    assert s == 201
    token3 = signup(api, "second@acme.example")
    uid3 = store.one("SELECT id FROM users WHERE email='second@acme.example'")["id"]
    store.q("INSERT OR REPLACE INTO org_members(user_id, org, role, created_at) VALUES(?,?,?,?)",
            (uid3, "Acme Safety", "member", _t.time()))
    s, out = call(api, "/api/scenes", method="GET", token=token3)
    assert any(sc["shared"] for sc in out["scenes"])

def test_workspace_update_endpoint(api):
    token = signup(api, "ws@example.com")
    s, out = call(api, "/api/scenes", {"name": "Lab A", "payload": {"workspace": {"kind": "lab", "objects": []}}}, token)
    assert s == 201; sid = out["id"]
    s, out = call(api, "/api/scenes/update", {"id": sid, "name": "Lab A2", "payload": {"workspace": {"kind": "lab", "objects": [1]}}}, token)
    assert s == 200
    s, out = call(api, "/api/scenes", method="GET", token=token)
    assert out["scenes"][0]["name"] == "Lab A2"
    token2 = signup(api, "other@example.com")
    s, out = call(api, "/api/scenes/update", {"id": sid, "name": "hijack", "payload": {}}, token2)
    assert s == 404  # cannot update someone else's workspace

def test_mcp_http_and_tools(api):
    s, out = call(api, "/api/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert s == 200 and out["result"]["serverInfo"]["name"] == "frontiersight-ai"
    s, out = call(api, "/api/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in out["result"]["tools"]]
    assert "analyse_scenario" in names and "simulate_counterfactual" in names
    s, out = call(api, "/api/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                    "params": {"name": "analyse_scenario", "arguments": {"name": "warehouse-near-miss"}}})
    pairs = out["result"]["structuredContent"]["pairs"]
    assert pairs and pairs[0]["measured"]["d_min"] is not None
    s, out = call(api, "/api/mcp", {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                    "params": {"name": "validate_scene", "arguments": {"scene": {"objects": [{"category": "dragon", "waypoints": [[1, 1]]}] * 2}}}})
    assert out["result"]["isError"] is True
    s, out = call(api, "/api/mcp", {"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert out["error"]["code"] == -32601

def test_scene_description_length_is_a_client_error(api):
    s, out = call(api, "/api/meta/scene", {"prompt": "x" * 4001})
    assert s == 400 and "4000" in out["error"]
    from integrations.meta.spark import generate_scene
    with pytest.raises(ValueError):
        generate_scene("y" * 4001)
