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


def _rsa_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    import base64 as b64
    def enc(n, size=None):
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return b64.urlsafe_b64encode(b).rstrip(b"=").decode()
    jwks = {"keys": [{"kty": "RSA", "kid": "test-kid", "n": enc(pub.n), "e": enc(pub.e)}]}
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return pem, jwks

def test_clerk_jwt_and_svix_verification(monkeypatch):
    import base64 as b64, time as _t
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from integrations import clerk_auth
    pem, jwks = _rsa_keys()
    monkeypatch.setattr(clerk_auth, "_fetch_jwks", lambda host: jwks)
    host = "example.clerk.accounts.dev"
    def b64u(b): return b64.urlsafe_b64encode(b).rstrip(b"=").decode()
    header = b64u(b'{"alg":"RS256","kid":"test-kid"}')
    claims = {"sub": "user_clerk123", "iss": f"https://{host}", "exp": _t.time() + 600}
    payload = b64u(json.dumps(claims).encode() if False else __import__("json").dumps(claims).encode())
    sig = load_pem_private_key(pem, None).sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    token = f"{header}.{payload}.{b64u(sig)}"
    out = clerk_auth.verify_session_token(token, host=host)
    assert out["sub"] == "user_clerk123"
    with pytest.raises(ValueError):
        clerk_auth.verify_session_token(token + "x", host=host)
    # svix webhook signature
    import hashlib as hl
    secret = "whsec_" + b64.b64encode(b"test-secret-key-0123456789").decode()
    body = b'{"type":"user.created","data":{"id":"user_clerk123"}}'
    ts = str(int(_t.time()))
    sigv = b64.b64encode(__import__("hmac").new(b"test-secret-key-0123456789",
                         f"msg_1.{ts}.".encode() + body, hl.sha256).digest()).decode()
    evt = clerk_auth.verify_svix(body, {"svix-id": "msg_1", "svix-timestamp": ts,
                                        "svix-signature": f"v1,{sigv}"}, secret=secret)
    assert evt["type"] == "user.created"
    with pytest.raises(ValueError):
        clerk_auth.verify_svix(body, {"svix-id": "msg_1", "svix-timestamp": ts,
                                      "svix-signature": "v1,forged"}, secret=secret)

def test_clerk_config_and_sync(api, monkeypatch):
    from services.api import store
    s, out = call(api, "/api/auth/config", method="GET")
    assert s == 200 and out["clerk_enabled"] is False  # no key in test env
    from services.api import mcp  # noqa: F401  (import surface sanity)
    import services.api.server as srv
    monkeypatch.setattr("integrations.clerk_auth.verify_session_token",
                        lambda tok: {"sub": "user_clerk123", "azp": "https://frontiersight-ai.vercel.app"})
    monkeypatch.setattr("integrations.clerk_auth.verified_profile",lambda uid: {"email":"ada@example.com","name":"Ada"})
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jb21c")
    # config now reports enabled (publishable key is server-config, read at call time)
    s, out = call(api, "/api/auth/config", method="GET")
    assert out["clerk_enabled"] is True
    s, out = call(api, "/api/auth/clerk-sync", {"email": "ada@example.com", "name": "Ada"},
                  headers={"Authorization": "Bearer faketoken"})
    assert s == 200 and out["plan"] == "explorer", out
    # the issued local session works with /api/me
    s, me = call(api, "/api/me", method="GET", token=out["token"])
    assert me["authenticated"] and me["user"]["email"] == "ada@example.com"
    u = store.one("SELECT clerk_id FROM users WHERE email='ada@example.com'")
    assert u["clerk_id"] == "user_clerk123"

def test_spark_scene_quality_gate():
    from integrations.meta.spark import scene_quality
    boring = [{"category": "forklift", "waypoints": [[1, 7], [6, 7]], "speed": 1.5, "radius": 0.9, "curve": "straight", "mode": "stop"},
              {"category": "pedestrian", "waypoints": [[13, 13], [13, 11]], "speed": 1.2, "radius": 0.45, "curve": "straight", "mode": "stop"}]
    q = scene_quality(boring)
    assert q["has_close_interaction"] is False and any("no close interaction" in i for i in q["issues"])
    collision = [{"category": "shelf", "waypoints": [[8, 7]], "speed": 0, "radius": 1.4, "curve": "straight", "mode": "stop"},
                 {"category": "forklift", "waypoints": [[2, 7], [14, 7]], "speed": 1.5, "radius": 0.9, "curve": "straight", "mode": "stop"},
                 {"category": "pedestrian", "waypoints": [[15, 1], [15, 3]], "speed": 1.0, "radius": 0.45, "curve": "straight", "mode": "stop"}]
    q2 = scene_quality(collision)
    assert any("footprint" in i for i in q2["issues"])

def test_voice_endpoint_validation_and_stub(api, monkeypatch):
    import base64 as b64, struct
    # minimal valid WAV header (mono 16-bit 24kHz) + silence
    def wav(seconds=0.1):
        n = int(24000 * seconds)
        hdr = b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16) + b"data" + struct.pack("<I", n * 2)
        return hdr + b"\x00\x00" * n
    good = "data:audio/wav;base64," + b64.b64encode(wav()).decode()
    s, out = call(api, "/api/meta/transcribe", {"audio_data_url": good})
    assert s in (202, 503)  # no key in test env -> BLOCKED_CREDENTIALS path (202) - never a crash
    if s == 202: assert out["status"] == "BLOCKED_CREDENTIALS"
    s, out = call(api, "/api/meta/transcribe", {"audio_data_url": "data:audio/wav;base64," + b64.b64encode(b"not a wav").decode()})
    assert s in (202, 400, 503)  # blocked-credentials is evaluated before validation order is an impl detail
    from integrations.meta import voice
    with pytest.raises(ValueError): voice.validate_wav(b"RIFFxxxxWAVEbad")
    facts = voice.validate_wav(wav(0.5))
    assert facts["sample_rate"] == 24000

def test_custom_objects_generate_and_profile(api, monkeypatch):
    from integrations.meta import spark
    monkeypatch.setattr(spark, "design_custom_object",
                        lambda d, model=None: ({"name": "Scissor Lift", "base_category": "vehicle", "radius": 1.0,
                                    "height_m": 2.6, "palette": {"body": "#f2b04a", "accent": "#38c6d9", "dark": "#2c3444"},
                                    "parts": [{"shape": "box", "size": [1.6, 0.4, 0.9], "pos": [0, 0.3, 0], "color": "body"}],
                                    "description": "test"}, {"model": "muse-spark-1.3"}))
    import services.api.server as srv
    monkeypatch.setattr("integrations.meta.image.generate_illustration",
                        lambda prompt, timeout: {"data": [{"b64_json": "AAAA"}], "model": "muse-image-1.0"})
    s, out = call(api, "/api/meta/object", {"description": "a yellow scissor lift"})
    assert s == 200 and out["spec"]["name"] == "Scissor Lift" and out["source"] == "MODEL_DERIVED"
    assert out["image_data_url"].startswith("data:image/webp")
    with pytest.raises(spark.ModelError):
        spark.validate_custom_object({"name": "X", "parts": [{"shape": "torus", "size": [1, 1, 1], "pos": [0, 0, 0]}]})
    # profile persistence: guest cannot sync, signed-in user can, and it lists back
    s, out = call(api, "/api/objects", {"spec": out["spec"] if False else {
        "name": "Scissor Lift", "base_category": "vehicle", "radius": 1.0, "height_m": 2.6,
        "palette": {"body": "#f2b04a", "accent": "#38c6d9", "dark": "#2c3444"},
        "parts": [{"shape": "box", "size": [1.6, 0.4, 0.9], "pos": [0, 0.3, 0], "color": "body"}]}})
    assert s == 401
    token = signup(api, "maker@example.com")
    spec = {"name": "Scissor Lift", "base_category": "vehicle", "radius": 1.0, "height_m": 2.6,
            "palette": {"body": "#f2b04a", "accent": "#38c6d9", "dark": "#2c3444"},
            "parts": [{"shape": "box", "size": [1.6, 0.4, 0.9], "pos": [0, 0.3, 0], "color": "body"}]}
    s, out = call(api, "/api/objects", {"spec": spec, "image": "data:image/jpeg;base64,AAAA"}, token)
    assert s == 201, out
    s, out = call(api, "/api/objects", method="GET", token=token)
    assert len(out["objects"]) == 1 and out["objects"][0]["spec"]["name"] == "Scissor Lift"

def test_clerk_cannot_link_existing_account_by_email_or_log_in_with_predictable_password(api,monkeypatch):
    from services.api import store
    signup(api,'victim@example.com')
    original=dict(store.one('SELECT * FROM users WHERE email=?',('victim@example.com',)))
    with pytest.raises(ValueError):store.provision_clerk_user('user_attacker','victim@example.com','Attacker')
    assert store.one('SELECT clerk_id FROM users WHERE id=?',(original['id'],))['clerk_id'] is None
    account=store.provision_clerk_user('user_new','new@example.com','New')
    assert not store.verify_password('clerk-managed-user_new',account['pw_hash'],account['pw_salt'])
    # Also deny password login for already-existing Clerk-managed accounts, even
    # if they predate the random-password migration.
    old_hash,old_salt=store.hash_password('clerk-managed-user_old')
    store.q('UPDATE users SET pw_hash=?,pw_salt=? WHERE id=?',(old_hash,old_salt,account['id']))
    assert call(api,'/api/auth/login',{'email':'new@example.com','password':'clerk-managed-user_old'})[0]==401

def test_clerk_sync_ignores_posted_identity_and_rejects_wrong_origin(api,monkeypatch):
    monkeypatch.setenv('CLERK_PUBLISHABLE_KEY','pk_test_example')
    monkeypatch.setattr('integrations.clerk_auth.verify_session_token',lambda tok:{'sub':'user_verified','azp':'https://frontiersight-ai.vercel.app'})
    monkeypatch.setattr('integrations.clerk_auth.verified_profile',lambda uid:{'email':'verified@example.com','name':'Verified'})
    status,result=call(api,'/api/auth/clerk-sync',{'email':'spoofed@example.com','name':'Spoofed'},headers={'Authorization':'Bearer fixture'})
    assert status==200 and result['user']['email']=='verified@example.com'
    monkeypatch.setattr('integrations.clerk_auth.verify_session_token',lambda tok:{'sub':'user_verified','azp':'https://other.example'})
    assert call(api,'/api/auth/clerk-sync',{},headers={'Authorization':'Bearer fixture'})[0]==401

def test_model_selection_validation(api, monkeypatch):
    from integrations.meta import spark
    assert spark.resolve_model(None) == spark.MODEL
    assert spark.resolve_model("muse-wonder-1.0") == "muse-wonder-1.0"
    with pytest.raises(ValueError): spark.resolve_model("muse-spark-9.9")
    s, out = call(api, "/api/meta/scene", {"prompt": "a forklift and a pedestrian in an aisle", "model": "gpt-9"})
    assert s == 400 and "unknown model" in out["error"]
    # a valid non-default model reaches the ( stubbed ) generator path cleanly
    monkeypatch.setattr(spark, "generate_scene",
                        lambda desc, model=None, candidates=3: ({"name": "T", "objects": [], "quality": {}}, {"model": model, "candidates_requested": candidates}))
    s, out = call(api, "/api/meta/scene", {"prompt": "a forklift and a pedestrian in an aisle", "model": "muse-spark-1.1"})
    assert s == 200 and out["model_call"]["model"] == "muse-spark-1.1"
    assert out["model_call"]["candidates_requested"] == 3
