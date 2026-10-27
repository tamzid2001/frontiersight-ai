"""FrontierSight API — zero-dependency stdlib HTTP server (local + Vercel).

MODEL_API_KEY is read server-side only and never serialised to clients.
Diagnostics report *whether* a key is configured, never the key."""
from __future__ import annotations
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import os
from engine import scenarios as scen
from engine.kinematics import Calibration, analyse_pair
from engine.validation import run_all as validation_cases
from agents.workflow import run_analysis
from integrations.meta import spark, sam
from integrations.meta.spark import BlockedCredentials, ModelError

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png"}
_cache: dict = {}
MAX_BODY = 12 * 1024 * 1024          # 12 MB hard ingest bound
RATE_LIMIT, RATE_WINDOW = 120, 60.0  # POST requests per IP per minute (best-effort, per-instance)
_hits: dict = {}

def _rate_ok(ip: str, limit: int = RATE_LIMIT) -> bool:
    import time
    now = time.time()
    bucket = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
    bucket.append(now); _hits[ip] = bucket[-limit * 2:]
    return len(bucket) <= limit

# --- accounts, billing, entitlements -------------------------------------
from services.api import store as _store
from integrations import billing as _billing

def _auth_user(handler):
    auth = handler.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    return _store.user_for_token(token)

def _plan_of(user) -> str:
    return _store.plan_for(user["id"]) if user else "explorer"

def _fernet():
    import base64, hashlib as _hl
    raw = os.environ.get("BYOK_ENCRYPTION_KEY", "").strip()
    if not raw: return None
    from cryptography.fernet import Fernet
    try: return Fernet(raw.encode())
    except Exception:
        return Fernet(base64.urlsafe_b64encode(_hl.sha256(raw.encode()).digest()))

def parse_tracks(payload: list):
    """Validate user-supplied tracks. Hard bounds; invalid input raises ValueError
    with a precise reason — never silently repaired into a plausible scene."""
    from engine.tracking import Track
    from engine.geometry import Vec
    if not isinstance(payload, list) or not 2 <= len(payload) <= 24:
        raise ValueError("tracks must be a list of 2..24 objects")
    tracks = []
    seen_ids = set()
    for raw in payload:
        if not isinstance(raw, dict): raise ValueError("each track must be an object")
        oid = str(raw.get("object_id", ""))[:64]
        if not oid or oid in seen_ids: raise ValueError(f"duplicate or missing object_id: {oid!r} (ids must be unique)")
        seen_ids.add(oid)
        if not 0 <= float(raw.get("radius", 0.0)) <= 100: raise ValueError(f"track {oid}: radius out of range [0,100]")
        pts = raw.get("points", [])
        if not isinstance(pts, list) or not 2 <= len(pts) <= 5000:
            raise ValueError(f"track {raw.get('object_id')}: need 2..5000 points")
        for pt in pts:
            if not (isinstance(pt, (list, tuple)) and len(pt) == 3
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pt)):
                raise ValueError(f"track {raw.get('object_id')}: each point must be [t, x, y] numbers")
        occ = raw.get("occluded", [])
        if not (isinstance(occ, list) and all(isinstance(o, (list, tuple)) and len(o) == 2
                and all(isinstance(v, (int, float)) for v in o) and o[0] <= o[1] for o in occ)):
            raise ValueError(f"track {raw.get('object_id')}: occluded must be [[t0, t1], ...] with t0 <= t1")
        points = [(float(t), Vec(float(x), float(y))) for t, x, y in pts]
        tracks.append(Track(str(raw.get("object_id", f"obj-{len(tracks)+1}"))[:64],
                            str(raw.get("category", "object"))[:32],
                            raw.get("space", "pixel"), points,
                            float(raw.get("radius", 0.0)), str(raw.get("source", "USER_UPLOADED"))[:32],
                            [tuple(o) for o in occ]))
    if len({tr.space for tr in tracks}) > 1:
        raise ValueError("all tracks must share one coordinate space")
    return tracks

def get_scenario(name: str) -> dict:
    if name not in _cache: _cache[name] = scen.build(name)
    return _cache[name]

def report_for(name: str, run_dict: dict | None = None) -> dict:
    sc = get_scenario(name)
    return {"experiment_id": f"fs-{name}", "kind": sc["kind"], "disclaimer": sc["disclaimer"],
            "source_digest": __import__("hashlib").sha256(
                json.dumps(scen.scenario_to_dict(sc), sort_keys=True).encode()).hexdigest(),
            "calibration": sc["calibration"], "ground_truth": sc["ground_truth"],
            "run": run_dict, "validation_cases": validation_cases(),
            "labels": {"deterministic_fixture_verified": True, "unit_tests": "see CI",
                       "meta_api_integration_verified": "see docs/LIVE_META_VERIFICATION.md",
                       "real_video_evaluation_completed": False, "hardware_validation": "unavailable",
                       "no_safety_certification_claimed": True}}

class H(BaseHTTPRequestHandler):
    server_version = "FrontierSight"
    sys_version = ""
    def version_string(self): return "FrontierSight"
    def log_message(self, *a): pass
    def _route(self) -> str:
        u = urlparse(self.path)
        ep = parse_qs(u.query).get("ep", [None])[0]
        return {"health": "/api/health", "diagnostics": "/api/diagnostics", "scenarios": "/api/scenarios",
                "robots": "/robots.txt", "sitemap": "/sitemap.xml", "logo": "/logo-mark.svg", "favicon": "/favicon-32.png",
                "analyze": "/api/analyze", "counterfactual": "/api/counterfactual", "report": "/api/report",
                "analyze-custom": "/api/analyze-custom", "counterfactual-custom": "/api/counterfactual-custom",
                "tracks": "/api/tracks", "from-paths": "/api/tracks/from-paths", "me": "/api/me", "signup": "/api/auth/signup",
                "login": "/api/auth/login", "logout": "/api/auth/logout",
                "checkout": "/api/billing/checkout", "portal": "/api/billing/portal",
                "webhook": "/api/billing/webhook", "metakey": "/api/keys/meta",
                "scenes": "/api/scenes", "scenedel": "/api/scenes/delete", "sceneupd": "/api/scenes/update",
                "waitlist": "/api/waitlist", "quote": "/api/sales/quote",
                "segment-video": "/api/meta/segment-video", "org": "/api/org", "support": "/api/support",
                "hypothesis": "/api/meta/hypothesis", "segment": "/api/meta/segment", "scene": "/api/meta/scene",
                "validate": "/api/validate", "home": "/", "css": "/app.css", "js": "/app.js"}.get(ep, u.path)
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Cache-Control", "no-store" if ctype == "application/json" else "no-cache")
        self.end_headers(); self.wfile.write(b)
    def _body(self) -> dict:
        def _bad_const(x): raise ValueError(f"non-finite JSON number not accepted: {x}")
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}",
                          parse_constant=_bad_const)
    def do_GET(self):
        route = self._route()
        try:
            if route in ("/robots.txt", "/sitemap.xml") or self.path.split("?")[0] in ("/robots.txt", "/sitemap.xml"):
                import datetime as _dt
                base = os.environ.get("APP_BASE_URL", "https://frontiersight-ai.vercel.app").rstrip("/")
                if route == "/robots.txt" or self.path.startswith("/robots.txt"):
                    return self._send(200, f"User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {base}/sitemap.xml\n".encode(), "text/plain")
                today = _dt.date.today().isoformat()
                xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                       '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                       'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
                       f' <url><loc>{base}/</loc><lastmod>{today}</lastmod>'
                       '<changefreq>weekly</changefreq><priority>1.0</priority>'
                       '<image:image><image:loc>https://i.ytimg.com/vi/mYTkPqigoz8/maxresdefault.jpg</image:loc>'
                       '<image:title>FrontierSight AI demo — forklift and pedestrian near-miss analysis</image:title></image:image></url>\n'
                       '</urlset>\n')
                return self._send(200, xml.encode(), "application/xml")
            if route.startswith("/api/health"): return self._send(200, {"ok": True, "service": "frontiersight-ai", "version": "0.20.0"})
            if route.startswith("/api/diagnostics"):
                return self._send(200, {"meta_configured": spark.configured(), "spark_model": spark.MODEL,
                                        "sam_model": sam.MODEL, "key_source": "server env MODEL_API_KEY (value never exposed)",
                                        "mode": "LIVE_META" if spark.configured() else "FIXTURE_REPLAY"})
            if route.startswith("/api/scenarios"):
                name = parse_qs(urlparse(self.path).query).get("name", [None])[0]
                if name: return self._send(200, scen.scenario_to_dict(get_scenario(name)))
                return self._send(200, {"scenarios": [{"id": n, "description": get_scenario(n)["description"]} for n in scen.SCENARIOS]})
            if route.startswith("/api/me"):
                user = _auth_user(self)
                if not user: return self._send(200, {"authenticated": False, "plan": "explorer",
                                                     "entitlements": _billing.entitlements("explorer"),
                                                     "billing_configured": _billing.configured()})
                plan = _plan_of(user)
                sub = _store.one("SELECT status, current_period_end, cancel_at_period_end FROM subscriptions WHERE user_id=?", (user["id"],))
                key = _store.one("SELECT last4 FROM user_keys WHERE user_id=?", (user["id"],))
                return self._send(200, {"authenticated": True, "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
                                        "plan": plan, "entitlements": _billing.entitlements(plan),
                                        "subscription": dict(sub) if sub else None,
                                        "meta_key": {"configured": bool(key), "last4": key["last4"] if key else None},
                                        "billing_configured": _billing.configured()})
            if route.startswith("/api/scenes") and not route.startswith("/api/scenes/delete"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required for server-saved scenes", "upgrade_url": "/#view-auth"})
                rows = _store.q("SELECT id, name, payload, created_at, org, user_id FROM scenes WHERE user_id=? ORDER BY created_at DESC", (user["id"],))
                scenes = [{"id": r["id"], "name": r["name"], "created_at": r["created_at"], "shared": False,
                           "payload": json.loads(r["payload"])} for r in rows]
                m = _store.one("SELECT org FROM org_members WHERE user_id=?", (user["id"],))
                if m:
                    shared = _store.q("SELECT id, name, payload, created_at FROM scenes WHERE org=? AND user_id!=? ORDER BY created_at DESC", (m["org"], user["id"]))
                    scenes += [{"id": r["id"], "name": r["name"], "created_at": r["created_at"], "shared": True,
                                "org": m["org"], "payload": json.loads(r["payload"])} for r in shared]
                return self._send(200, {"scenes": scenes, "plan": _plan_of(user), "org": m["org"] if m else None})
            if route.startswith("/api/org"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required"})
                m = _store.one("SELECT org, role FROM org_members WHERE user_id=?", (user["id"],))
                if not m: return self._send(200, {"org": None, "note": "no organisation — Team plans are provisioned per contract (see Pricing)"})
                members = _store.q("SELECT u.email, om.role AS role FROM org_members om JOIN users u ON u.id=om.user_id WHERE om.org=?", (m["org"],))
                shared = _store.q("SELECT id, name, created_at, user_id FROM scenes WHERE org=? ORDER BY created_at DESC LIMIT 50", (m["org"],))
                audit = _store.q("SELECT action, detail, ts FROM audit_log WHERE org=? ORDER BY ts DESC LIMIT 100", (m["org"],)) \
                    if _plan_of(user) == "team" else []
                return self._send(200, {"org": m["org"], "role": m["role"],
                                        "members": [dict(r) for r in members],
                                        "shared_scenes": [dict(r) for r in shared],
                                        "audit_log": [dict(r) for r in audit]})
            if route.startswith("/api/validate"): return self._send(200, {"cases": validation_cases()})
            if route.startswith("/api/report"):
                name = parse_qs(urlparse(self.path).query).get("name", ["warehouse-near-miss"])[0]
                return self._send(200, report_for(name))
            name = "index.html" if route in ("/", "") else route.lstrip("/").split("?")[0]
            f = (WEB / name).resolve()
            if f.is_file() and f.suffix in TYPES and f.is_relative_to(WEB.resolve()):
                return self._send(200, f.read_bytes(), TYPES[f.suffix])
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(400, {"error": str(e)[:300]})
    def do_POST(self):
        route = self._route()
        try:
            if route.startswith("/api/billing/webhook"):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
                try:
                    event = _billing.verify_webhook(raw, self.headers.get("Stripe-Signature", ""))
                except _billing.BillingNotConfigured as e:
                    return self._send(503, {"error": str(e), "code": e.code})
                except ValueError as e:
                    return self._send(400, {"error": f"webhook rejected: {e}"})
                ev_id = event.get("id", "")
                if _store.one("SELECT id FROM stripe_events WHERE id=?", (ev_id,)):
                    return self._send(200, {"received": True, "duplicate": True})
                _store.q("INSERT INTO stripe_events(id, processed_at) VALUES(?,?)", (ev_id, __import__("time").time()))
                obj = (event.get("data") or {}).get("object") or {}
                etype = event.get("type", "")
                import time as _time
                if etype == "checkout.session.completed":
                    uid = int(obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id") or 0)
                    if uid:
                        _store.q("INSERT OR REPLACE INTO subscriptions(user_id, stripe_customer_id, stripe_sub_id, status, updated_at) VALUES(?,?,?,?,?)",
                                 (uid, obj.get("customer"), obj.get("subscription"), "active", _time.time()))
                        _store.audit(uid, "subscribed", str(obj.get("subscription")))
                elif etype.startswith("customer.subscription."):
                    uid = int((obj.get("metadata") or {}).get("user_id") or 0)
                    items = ((obj.get("items") or {}).get("data") or [{}])
                    price_id = ((items[0].get("price") or {}).get("id")) if items else None
                    if uid:
                        _store.q("INSERT OR REPLACE INTO subscriptions(user_id, stripe_customer_id, stripe_sub_id, price_id, status, current_period_end, cancel_at_period_end, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                                 (uid, obj.get("customer"), obj.get("id"), price_id, obj.get("status"),
                                  obj.get("current_period_end"), 1 if obj.get("cancel_at_period_end") else 0, _time.time()))
                elif etype == "invoice.payment_failed":
                    _store.q("UPDATE subscriptions SET status='past_due', updated_at=? WHERE stripe_customer_id=?",
                             (_time.time(), obj.get("customer")))
                return self._send(200, {"received": True, "type": etype})
            if int(self.headers.get("Content-Length", 0) or 0) > MAX_BODY:
                return self._send(413, {"error": f"payload exceeds {MAX_BODY // (1024*1024)} MB ingest bound"})
            if not _rate_ok(self.client_address[0]):
                return self._send(429, {"error": "rate limit exceeded (120 POST/min per client)"})
            if route.startswith("/api/meta/") and not _rate_ok("meta:" + self.client_address[0], limit=30):
                return self._send(429, {"error": "model endpoint quota exceeded (30 POST/min per client) — these calls spend the host's Meta API credits"})
            body = self._body()
            if route.startswith("/api/analyze-custom"):
                tracks = parse_tracks(body.get("tracks", []))
                mpp = body.get("metres_per_pixel")
                if mpp is not None:
                    from engine.kinematics import to_world as _tw
                    _cal = Calibration(float(mpp)); _cal.validate()
                    tracks = [_tw(t, _cal) for t in tracks]
                custom = {"id": str(body.get("id", "custom-scene"))[:64], "kind": "USER_UPLOADED",
                          "calibration": {"metres_per_pixel": mpp, "frame": body.get("frame", "user-supplied")},
                          "tracks": tracks, "ground_truth": {}, "description": "user-uploaded scene",
                          "disclaimer": "User-uploaded scene; no ground truth held. Metric claims only if calibration declared."}
                run = run_analysis(custom, float(body.get("speed_reduction_pct", 40)),
                                   float(body.get("intervention_t", 1.0)), bool(body.get("human_approved", False)),
                                   body.get("idempotency_key"))
                return self._send(200, {"run": run.to_dict(), "scenario": scen.scenario_to_dict(custom)})
            if route.startswith("/api/counterfactual-custom"):
                from engine.pathsim import simulate_on_paths
                tracks = parse_tracks(body.get("tracks", []))
                agent_id = body.get("agent_id", tracks[0].object_id)
                agent = next((t for t in tracks if t.object_id == agent_id), None)
                if agent is None: return self._send(400, {"error": f"unknown agent_id: {agent_id}"})
                _others = [t for t in tracks if t.object_id != agent.object_id]
                _mc_req = int(body.get("mc_runs", 100))
                _mc_limit = _billing.entitlements(_plan_of(_auth_user(self)))["mc_runs"]
                if _mc_limit is not None and _mc_req > _mc_limit:
                    raise _billing.PaymentRequired(f"mc_runs (limit {_mc_limit})", _plan_of(_auth_user(self)))
                r = simulate_on_paths(agent, _others, float(body.get("intervention_t", 1.0)),
                                      float(body.get("speed_reduction_pct", 40)),
                                      braking_decel=float(body.get("braking_decel", 2.5)),
                                      position_sigma=0.15, mc_runs=_mc_req, seed=42)
                return self._send(200, r)
            if route.startswith("/api/tracks/from-paths"):
                from engine.curves import sample_tracks
                objs = body.get("objects", [])
                if not isinstance(objs, list) or not 1 <= len(objs) <= 24:
                    return self._send(400, {"error": "objects must be a list of 1..24 path definitions"})
                for o in objs:
                    wps = o.get("waypoints", [])
                    if not 1 <= len(wps) <= 24: return self._send(400, {"error": f"{o.get('category','object')}: need 1..24 waypoints"})
                    if o.get("curve", "straight") not in ("straight", "smooth"):
                        return self._send(400, {"error": "curve must be 'straight' or 'smooth'"})
                tracks = sample_tracks(objs)
                return self._send(200, {"tracks": [scen.track_to_dict(t) for t in tracks],
                                        "note": "sampled server-side by engine/curves (Catmull-Rom, arc-length parameterised)"})
            if route.startswith("/api/tracks"):
                from engine.iou_tracking import build_tracks
                built = build_tracks(body.get("frames", []), str(body.get("category", "object"))[:32],
                                     float(body.get("iou_threshold", 0.2)))
                return self._send(200, {"tracks": [scen.track_to_dict(t) for t in built],
                                        "note": "MODEL_DERIVED tracks associated by greedy IoU (engine/iou_tracking.py); pixel space"})
            if route.startswith("/api/analyze"):
                sc = get_scenario(body.get("scenario", "warehouse-near-miss"))
                run = run_analysis(sc, float(body.get("speed_reduction_pct", 40)),
                                   float(body.get("intervention_t", 1.0)),
                                   bool(body.get("human_approved", False)),
                                   body.get("idempotency_key"))
                return self._send(200, {"run": run.to_dict(), "scenario": scen.scenario_to_dict(sc)})
            if route.startswith("/api/counterfactual"):
                sc = get_scenario(body.get("scenario", "warehouse-near-miss"))
                by_id = {t.object_id: t for t in sc["tracks"]}
                agent = by_id.get(body.get("agent_id"), sc["tracks"][0])
                target = body.get("target_id")
                others = [t for t in sc["tracks"] if t.object_id != agent.object_id
                          and (not target or t.object_id == target)]
                if not others: return self._send(400, {"error": "no comparison actor selected"})
                _mc_req = int(body.get("mc_runs", 200))
                _mc_limit = _billing.entitlements(_plan_of(_auth_user(self)))["mc_runs"]
                if _mc_limit is not None and _mc_req > _mc_limit:
                    raise _billing.PaymentRequired(f"mc_runs (limit {_mc_limit})", _plan_of(_auth_user(self)))
                from engine.pathsim import simulate_on_paths
                out = simulate_on_paths(agent, others, float(body.get("intervention_t", 1.0)),
                                        float(body.get("speed_reduction_pct", 40)),
                                        braking_decel=float(body.get("braking_decel", 2.5)),
                                        position_sigma=0.15, mc_runs=_mc_req, seed=42)
                return self._send(200, out)
            if route.startswith("/api/meta/hypothesis"):
                sc = get_scenario(body.get("scenario", "warehouse-near-miss"))
                cal = Calibration(sc["calibration"].get("metres_per_pixel"))
                pairs = [analyse_pair(a, b, cal) for i, a in enumerate(sc["tracks"]) for b in sc["tracks"][i + 1:]]
                obj, meta = spark.propose_hypothesis({"pairs": pairs})
                return self._send(200, {"hypothesis": obj, "model_call": meta, "source": "MODEL_DERIVED"})
            if route.startswith("/api/meta/scene"):
                from agents.scene_heuristic import match as _match
                desc = str(body.get("prompt", ""))
                try:
                    scene, meta = spark.generate_scene(desc)
                    return self._send(200, {"scene": scene, "source": "MODEL_DERIVED", "model_call": meta})
                except BlockedCredentials:
                    scene = _match(desc)
                    if scene: return self._send(200, {"scene": scene, "source": "OFFLINE_HEURISTIC", "model_call": None})
                    return self._send(202, {"status": "BLOCKED_CREDENTIALS",
                                            "detail": "Meta API not configured and no offline template matched. Try mentioning a warehouse near-miss, a road crossing, or a robot cell — or add MODEL_API_KEY."})
            if route.startswith("/api/auth/signup"):
                email = str(body.get("email", "")).strip().lower()
                name = str(body.get("name", "")).strip()
                password = str(body.get("password", ""))
                if len(name) < 2 or "@" not in email or len(password) < 8:
                    return self._send(400, {"error": "name (2+ chars), a valid email, and a password of 8+ characters are required"})
                if _store.one("SELECT id FROM users WHERE email=?", (email,)):
                    return self._send(409, {"error": "an account with this email already exists — sign in"})
                pw_hash, pw_salt = _store.hash_password(password)
                _store.q("INSERT INTO users(email, name, pw_hash, pw_salt, created_at) VALUES(?,?,?,?,?)",
                         (email, name, pw_hash, pw_salt, __import__("time").time()))
                user = dict(_store.one("SELECT * FROM users WHERE email=?", (email,)))
                _store.audit(user["id"], "signup")
                return self._send(201, {"token": _store.new_session(user["id"]),
                                        "user": {"id": user["id"], "name": name, "email": email}, "plan": "explorer"})
            if route.startswith("/api/auth/login"):
                email = str(body.get("email", "")).strip().lower()
                row = _store.one("SELECT * FROM users WHERE email=?", (email,))
                if not row or not _store.verify_password(str(body.get("password", "")), row["pw_hash"], row["pw_salt"]):
                    return self._send(401, {"error": "invalid email or password"})
                user = dict(row)
                return self._send(200, {"token": _store.new_session(user["id"]),
                                        "user": {"id": user["id"], "name": user["name"], "email": email},
                                        "plan": _plan_of(user)})
            if route.startswith("/api/auth/logout"):
                user = _auth_user(self)
                if user:
                    import hashlib as _hl
                    tok = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                    _store.q("DELETE FROM sessions WHERE token_hash=?", (_hl.sha256(tok.encode()).hexdigest(),))
                return self._send(200, {"ok": True})
            if route.startswith("/api/support"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in to open a support request"})
                subject = str(body.get("subject", "")).strip(); message = str(body.get("message", "")).strip()
                if len(subject) < 3 or len(message) < 10:
                    return self._send(400, {"error": "subject (3+ chars) and message (10+ chars) are required"})
                plan = _plan_of(user)
                _store.q("INSERT INTO support_tickets(user_id, subject, message, plan, created_at) VALUES(?,?,?,?,?)",
                         (user["id"], subject[:200], message[:5000], plan, __import__("time").time()))
                _store.audit(user["id"], "support_opened", subject[:80])
                return self._send(201, {"ok": True,
                    "priority": plan in ("researcher", "team"),
                    "note": ("priority queue (Researcher/Team)" if plan in ("researcher", "team")
                             else "standard queue (Explorer)") + " — requests are recorded on this deployment and answered by email in production"})
            if route.startswith("/api/waitlist"):
                _store.q("INSERT INTO waitlist(email, plan, created_at) VALUES(?,?,?)",
                         (str(body.get("email", ""))[:200], str(body.get("plan", ""))[:40], __import__("time").time()))
                return self._send(201, {"ok": True, "note": "waitlist recorded on this deployment"})
            if route.startswith("/api/sales/quote"):
                if not str(body.get("email", "")).strip() or not str(body.get("company", "")).strip():
                    return self._send(400, {"error": "company and work email are required"})
                _store.q("INSERT INTO quotes(company, email, seats, needs, created_at) VALUES(?,?,?,?,?)",
                         (str(body["company"])[:200], str(body["email"])[:200], str(body.get("seats", ""))[:40],
                          str(body.get("needs", ""))[:2000], __import__("time").time()))
                return self._send(201, {"ok": True, "note": "quote request recorded; in production this also emails the sales contact"})
            if route.startswith("/api/billing/checkout"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in before subscribing", "upgrade_url": "/#view-auth"})
                price_env = "PRICE_RESEARCHER_ANNUAL" if body.get("period") == "annual" else "PRICE_RESEARCHER_MONTHLY"
                base = os.environ.get("APP_BASE_URL", "https://frontiersight-ai.vercel.app")
                out = _billing.create_checkout(user, os.environ.get(price_env, ""),
                                               base + "/?billing=success", base + "/?billing=cancelled")
                return self._send(200, {"url": out.get("url"), "session_id": out.get("id")})
            if route.startswith("/api/billing/portal"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required"})
                sub = _store.one("SELECT stripe_customer_id FROM subscriptions WHERE user_id=?", (user["id"],))
                if not sub or not sub["stripe_customer_id"]:
                    return self._send(400, {"error": "no billing account yet — subscribe first"})
                base = os.environ.get("APP_BASE_URL", "https://frontiersight-ai.vercel.app")
                out = _billing.create_portal(sub["stripe_customer_id"], base + "/?billing=manage")
                return self._send(200, {"url": out.get("url")})
            if route.startswith("/api/keys/meta"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required"})
                plan = _plan_of(user)
                if not _billing.entitlements(plan)["byok"]:
                    raise _billing.PaymentRequired("byok", plan)
                f = _fernet()
                key = str(body.get("key", "")).strip()
                if body.get("delete"):
                    _store.q("DELETE FROM user_keys WHERE user_id=?", (user["id"],))
                    return self._send(200, {"ok": True, "configured": False})
                if not key: return self._send(400, {"error": "key is required (or {delete:true})"})
                if f is None:
                    return self._send(503, {"error": "BYOK_NOT_CONFIGURED: this deployment has no BYOK_ENCRYPTION_KEY set"})
                _store.q("INSERT OR REPLACE INTO user_keys(user_id, kind, ciphertext, last4, updated_at) VALUES(?,?,?,?,?)",
                         (user["id"], "meta", f.encrypt(key.encode()).decode(), key[-4:], __import__("time").time()))
                _store.audit(user["id"], "byok_saved")
                return self._send(200, {"ok": True, "configured": True, "last4": key[-4:]})
            if route.startswith("/api/scenes/update"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required"})
                sid = str(body.get("id", ""))
                row = _store.one("SELECT id FROM scenes WHERE id=? AND user_id=?", (sid, user["id"]))
                if not row: return self._send(404, {"error": "workspace not found (or not yours)"})
                payload = body.get("payload")
                if not isinstance(payload, dict):
                    return self._send(400, {"error": "payload must be a workspace object"})
                _store.q("UPDATE scenes SET name=?, payload=? WHERE id=? AND user_id=?",
                         (str(body.get("name", "workspace"))[:120], json.dumps(payload)[:2_000_000], sid, user["id"]))
                _store.audit(user["id"], "workspace_updated", sid)
                return self._send(200, {"ok": True, "id": sid})
            if route.startswith("/api/scenes/delete"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required"})
                _store.q("DELETE FROM scenes WHERE id=? AND user_id=?", (str(body.get("id", "")), user["id"]))
                return self._send(200, {"ok": True})
            if route.startswith("/api/scenes"):
                user = _auth_user(self)
                if not user: return self._send(401, {"error": "sign in required for server-saved scenes", "upgrade_url": "/#view-auth"})
                plan = _plan_of(user); limit = _billing.entitlements(plan)["server_scenes"]
                payload = body.get("payload")
                if not isinstance(payload, dict) or not any(k in payload for k in ("objects", "tracks", "workspace")):
                    return self._send(400, {"error": "payload must be a scene/workspace object ({objects:[...]}, {tracks:[...]} or {workspace:{...}})"})
                if limit is not None:
                    count = _store.one("SELECT COUNT(*) AS c FROM scenes WHERE user_id=?", (user["id"],))["c"]
                    if count >= limit:
                        raise _billing.PaymentRequired(f"server_scenes (limit {limit})", plan)
                import uuid as _uuid
                sid = _uuid.uuid4().hex[:16]
                _m = _store.one("SELECT org FROM org_members WHERE user_id=?", (user["id"],))
                _store.q("INSERT INTO scenes(id, user_id, name, payload, created_at, org) VALUES(?,?,?,?,?,?)",
                         (sid, user["id"], str(body.get("name", "scene"))[:120], json.dumps(payload)[:2_000_000],
                          __import__("time").time(), _m["org"] if _m else None))
                _store.audit(user["id"], "scene_saved", sid, org=_m["org"] if _m else "")
                return self._send(201, {"id": sid, "plan": plan, "limit": limit})
            if route.startswith("/api/meta/segment-video"):
                user = _auth_user(self)
                plan = _plan_of(user)
                if not _billing.entitlements(plan)["sam_video"]:
                    raise _billing.PaymentRequired("sam_video", plan)
                ref = body.get("file_id") or body.get("video_url", "")
                if not ref: return self._send(400, {"error": "video_url or file_id is required"})
                out = sam.segment_video(ref, body.get("concept", "person"), is_file_id=bool(body.get("file_id")))
                return self._send(200, out)
            if route.startswith("/api/meta/segment"):
                out = sam.segment_image(body["image_data_url"], body.get("concept", "person"))
                return self._send(200, out)
            return self._send(404, {"error": "not found"})
        except _billing.PaymentRequired as e:
            return self._send(402, {"error": str(e), "capability": e.capability, "plan": e.plan,
                                    "upgrade_url": "/#view-pricing"})
        except _billing.BillingNotConfigured as e:
            return self._send(503, {"error": str(e), "code": e.code})
        except BlockedCredentials as e:
            return self._send(202, {"status": "BLOCKED_CREDENTIALS", "detail": str(e)})
        except (ModelError, RuntimeError) as e:
            return self._send(502, {"status": "MODEL_ERROR", "detail": str(e)[:300]})
        except Exception as e:
            return self._send(400, {"error": str(e)[:300]})

H.do_PUT = H.do_POST
H.do_DELETE = H.do_POST

def main(argv=None) -> int:
    p = argparse.ArgumentParser(); p.add_argument("--port", type=int, default=8000)
    p.add_argument("--smoke", action="store_true"); a = p.parse_args(argv)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    if a.smoke:
        import threading, urllib.request
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        h = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/api/health", timeout=5).read())
        page = urllib.request.urlopen(f"http://127.0.0.1:{a.port}/", timeout=5).read().decode()
        assert h["ok"] and "FrontierSight" in page; print("smoke ok: health + UI served"); srv.shutdown(); return 0
    print(f"FrontierSight AI on http://127.0.0.1:{a.port}"); srv.serve_forever(); return 0

if __name__ == "__main__":
    raise SystemExit(main())
