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
