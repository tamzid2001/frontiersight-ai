"""FrontierSight API — zero-dependency stdlib HTTP server (local + Vercel).

MODEL_API_KEY is read server-side only and never serialised to clients.
Diagnostics report *whether* a key is configured, never the key."""
from __future__ import annotations
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from engine import scenarios as scen
from engine.kinematics import Calibration, analyse_pair
from engine.validation import run_all as validation_cases
from agents.workflow import run_analysis
from integrations.meta import spark, sam
from integrations.meta.spark import BlockedCredentials, ModelError

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
_cache: dict = {}
MAX_BODY = 12 * 1024 * 1024          # 12 MB hard ingest bound
RATE_LIMIT, RATE_WINDOW = 120, 60.0  # POST requests per IP per minute (best-effort, per-instance)
_hits: dict = {}

def _rate_ok(ip: str) -> bool:
    import time
    now = time.time()
    bucket = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
    bucket.append(now); _hits[ip] = bucket
    return len(bucket) <= RATE_LIMIT

def parse_tracks(payload: list):
    """Validate user-supplied tracks. Hard bounds; invalid input raises ValueError
    with a precise reason — never silently repaired into a plausible scene."""
    from engine.tracking import Track
    from engine.geometry import Vec
    if not isinstance(payload, list) or not 2 <= len(payload) <= 24:
        raise ValueError("tracks must be a list of 2..24 objects")
    tracks = []
    for raw in payload:
        pts = raw.get("points", [])
        if not 2 <= len(pts) <= 5000: raise ValueError(f"track {raw.get('object_id')}: need 2..5000 points")
        points = [(float(t), Vec(float(x), float(y))) for t, x, y in pts]
        tracks.append(Track(str(raw.get("object_id", f"obj-{len(tracks)+1}"))[:64],
                            str(raw.get("category", "object"))[:32],
                            raw.get("space", "pixel"), points,
                            float(raw.get("radius", 0.0)), str(raw.get("source", "USER_UPLOADED"))[:32],
                            [tuple(o) for o in raw.get("occluded", [])]))
    return tracks

def get_scenario(name: str) -> dict:
    if name not in _cache: _cache[name] = scen.build(name)
    return _cache[name]

def report_for(name: str, run_dict: dict | None = None) -> dict:
    sc = get_scenario(name)
    return {"experiment_id": f"fs-{name}", "kind": sc["kind"], "disclaimer": sc["disclaimer"],
            "source_digest": __import__("hashlib").sha256(name.encode()).hexdigest(),
            "calibration": sc["calibration"], "ground_truth": sc["ground_truth"],
            "run": run_dict, "validation_cases": validation_cases(),
            "labels": {"deterministic_fixture_verified": True, "unit_tests": "see CI",
                       "meta_api_integration_verified": "see docs/LIVE_META_VERIFICATION.md",
                       "real_video_evaluation_completed": False, "hardware_validation": "unavailable",
                       "no_safety_certification_claimed": True}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _route(self) -> str:
        u = urlparse(self.path)
        ep = parse_qs(u.query).get("ep", [None])[0]
        return {"health": "/api/health", "diagnostics": "/api/diagnostics", "scenarios": "/api/scenarios",
                "analyze": "/api/analyze", "counterfactual": "/api/counterfactual", "report": "/api/report",
                "analyze-custom": "/api/analyze-custom", "counterfactual-custom": "/api/counterfactual-custom",
                "tracks": "/api/tracks",
                "hypothesis": "/api/meta/hypothesis", "segment": "/api/meta/segment", "scene": "/api/meta/scene",
                "validate": "/api/validate", "home": "/", "css": "/app.css", "js": "/app.js"}.get(ep, u.path)
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
    def do_GET(self):
        route = self._route()
        try:
            if route.startswith("/api/health"): return self._send(200, {"ok": True, "service": "frontiersight-ai", "version": "0.4.1"})
            if route.startswith("/api/diagnostics"):
                return self._send(200, {"meta_configured": spark.configured(), "spark_model": spark.MODEL,
                                        "sam_model": sam.MODEL, "key_source": "server env MODEL_API_KEY (value never exposed)",
                                        "mode": "LIVE_META" if spark.configured() else "FIXTURE_REPLAY"})
            if route.startswith("/api/scenarios"):
                name = parse_qs(urlparse(self.path).query).get("name", [None])[0]
                if name: return self._send(200, scen.scenario_to_dict(get_scenario(name)))
                return self._send(200, {"scenarios": [{"id": n, "description": get_scenario(n)["description"]} for n in scen.SCENARIOS]})
            if route.startswith("/api/validate"): return self._send(200, {"cases": validation_cases()})
            if route.startswith("/api/report"):
                name = parse_qs(urlparse(self.path).query).get("name", ["warehouse-near-miss"])[0]
                return self._send(200, report_for(name))
            name = "index.html" if route in ("/", "") else route.lstrip("/").split("?")[0]
            f = WEB / name
            if f.is_file() and f.suffix in TYPES: return self._send(200, f.read_bytes(), TYPES[f.suffix])
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(400, {"error": str(e)[:300]})
    def do_POST(self):
        route = self._route()
        try:
            if int(self.headers.get("Content-Length", 0) or 0) > MAX_BODY:
                return self._send(413, {"error": f"payload exceeds {MAX_BODY // (1024*1024)} MB ingest bound"})
            if not _rate_ok(self.client_address[0]):
                return self._send(429, {"error": "rate limit exceeded (120 POST/min per client)"})
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
                from engine.counterfactual import SimParams
                from engine.multi import simulate_agent
                tracks = parse_tracks(body.get("tracks", []))
                agent_id = body.get("agent_id", tracks[0].object_id)
                agent = next((t for t in tracks if t.object_id == agent_id), tracks[0])
                t0 = agent.points[0][0]
                others = [(t.object_id, t.position_at(max(t0, t.points[0][0])),
                           t.velocity_at(1) if len(t.points) > 1 else __import__("engine.geometry", fromlist=["Vec"]).Vec(0, 0),
                           t.radius) for t in tracks if t.object_id != agent.object_id]
                r = simulate_agent((agent.position_at(t0), agent.velocity_at(1), agent.radius), others,
                                   float(body.get("intervention_t", 1.0)), float(body.get("speed_reduction_pct", 40)),
                                   SimParams(duration=6.0, dt=0.02))
                return self._send(200, r)
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
                from engine.geometry import Vec
                from engine.counterfactual import SimParams, simulate
                sc = get_scenario(body.get("scenario", "warehouse-near-miss"))
                agent, other = sc["tracks"][0], sc["tracks"][1]
                t0 = max(agent.points[0][0], other.points[0][0])
                r = simulate(agent.position_at(t0), agent.velocity_at(1), other.position_at(t0), other.velocity_at(1),
                             float(body.get("intervention_t", 1.0)), float(body.get("speed_reduction_pct", 40)),
                             SimParams(duration=6.0, dt=0.02), agent.radius, other.radius,
                             position_sigma=0.15, mc_runs=200, seed=42)
                return self._send(200, r)
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
            if route.startswith("/api/meta/segment"):
                out = sam.segment_image(body["image_data_url"], body.get("concept", "person"))
                return self._send(200, out)
            return self._send(404, {"error": "not found"})
        except BlockedCredentials as e:
            return self._send(202, {"status": "BLOCKED_CREDENTIALS", "detail": str(e)})
        except (ModelError, RuntimeError) as e:
            return self._send(502, {"status": "MODEL_ERROR", "detail": str(e)[:300]})
        except Exception as e:
            return self._send(400, {"error": str(e)[:300]})

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
