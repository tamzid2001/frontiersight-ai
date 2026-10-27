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
                "hypothesis": "/api/meta/hypothesis", "segment": "/api/meta/segment",
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
            if route.startswith("/api/health"): return self._send(200, {"ok": True, "service": "frontiersight-ai", "version": "0.1.1"})
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
            body = self._body()
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
