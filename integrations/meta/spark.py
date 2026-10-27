"""Muse Spark via Meta Model API (Responses API, https://api.meta.ai/v1).

Used for: scene interpretation, hypothesis generation, and narrating
*independently computed* findings. Structured output is validated against a
local schema; invalid model JSON is rejected, never repaired into a claim.
The model must not invent detections, measurements, or verdicts — prompts say
so, and the engine never reads its numbers back as measurements."""
from __future__ import annotations
import json, os, time, urllib.request, urllib.error, uuid

BASE = os.environ.get("META_API_BASE", "https://api.meta.ai/v1")
MODEL = os.environ.get("META_MODEL", "muse-spark-1.3")

class BlockedCredentials(RuntimeError): pass
class ModelError(RuntimeError): pass

def configured() -> bool:
    return bool(os.environ.get("MODEL_API_KEY", "").strip())

def _call(prompt: str, timeout: int = 60, retries: int = 2) -> tuple[str, dict]:
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    req_id = str(uuid.uuid4())
    body = json.dumps({"model": MODEL, "input": prompt}).encode()
    last = None
    for attempt in range(retries + 1):
        started = time.time()
        req = urllib.request.Request(BASE + "/responses", data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "X-Request-Id": req_id})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read().decode())
            text = out.get("output_text") or ""
            if not text:
                for item in out.get("output", []):
                    for c in item.get("content", []):
                        if c.get("text"): text += c["text"]
            meta = {"model": MODEL, "request_id": req_id, "attempt": attempt,
                    "latency_ms": round((time.time() - started) * 1000),
                    "usage": out.get("usage"), "response_id": out.get("id")}
            return text, meta
        except urllib.error.HTTPError as e:
            last = ModelError(f"Meta Model API HTTP {e.code}: {e.read().decode()[:300]}")
            if e.code not in (429, 500, 502, 503) or attempt == retries: raise last
        except Exception as e:  # timeouts etc. — bounded retry, then surface
            last = ModelError(f"Meta Model API error: {e}")
            if attempt == retries: raise last
        time.sleep(1.5 * (attempt + 1))
    raise last

HYPOTHESIS_SCHEMA = {"hypothesis": str, "intervention": dict, "rationale": str}

def propose_hypothesis(findings: dict) -> tuple[dict, dict]:
    """Ask Muse Spark for a counterfactual hypothesis as strict JSON.
    Returns (hypothesis, call_metadata). Raises ModelError on bad JSON/schema."""
    prompt = ("You are the Counterfactual Designer in a physical-AI safety research tool. "
              "Given these DETERMINISTIC findings (do not recompute or contradict them), propose ONE "
              "counterfactual intervention for the moving agent. Reply with ONLY a JSON object: "
              '{"hypothesis": str, "intervention": {"speed_reduction_pct": number 0-80, '
              '"intervention_time_s": number >= 0}, "rationale": str}. '
              "Findings:\n" + json.dumps(findings)[:5000])
    text, meta = _call(prompt, timeout=30, retries=1)
    try:
        obj = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception as e:
        raise ModelError(f"model did not return JSON: {e}") from e
    for k, typ in HYPOTHESIS_SCHEMA.items():
        if not isinstance(obj.get(k), typ): raise ModelError(f"schema violation: {k} must be {typ.__name__}")
    iv = obj["intervention"]
    if not (0 <= float(iv.get("speed_reduction_pct", -1)) <= 80 and float(iv.get("intervention_time_s", -1)) >= 0):
        raise ModelError("schema violation: intervention out of bounds")
    return obj, meta

SCENE_CATEGORIES = {"forklift", "pedestrian", "robot", "vehicle", "cyclist", "shelf"}
STAGE = (16.0, 14.0)

def validate_scene(obj: dict) -> dict:
    """Strict validation of a model-generated scene. Any violation raises
    ModelError — a malformed scene is rejected, never repaired into place."""
    objs = obj.get("objects")
    if not isinstance(objs, list) or not 2 <= len(objs) <= 8:
        raise ModelError("scene must contain 2..8 objects")
    out = []
    for i, o in enumerate(objs):
        cat = o.get("category")
        if cat not in SCENE_CATEGORIES: raise ModelError(f"object {i}: unknown category {cat!r}")
        wps = o.get("waypoints")
        if not isinstance(wps, list) or not (1 <= len(wps) <= 24):
            raise ModelError(f"object {i}: need 1..24 waypoints")
        pts = []
        for w in wps:
            if not (isinstance(w, (list, tuple)) and len(w) == 2): raise ModelError(f"object {i}: bad waypoint {w!r}")
            x, y = float(w[0]), float(w[1])
            if not (0 <= x <= STAGE[0] and 0 <= y <= STAGE[1]): raise ModelError(f"object {i}: waypoint {(x, y)} outside stage")
            pts.append([round(x, 2), round(y, 2)])
        speed = float(o.get("speed", 0 if cat == "shelf" else 1.2))
        radius = float(o.get("radius", 1.1 if cat == "shelf" else 0.6))
        delay = float(o.get("delay", 0))
        if not 0 <= speed <= 8: raise ModelError(f"object {i}: speed out of range")
        if not 0.1 <= radius <= 3: raise ModelError(f"object {i}: radius out of range")
        if not 0 <= delay <= 10: raise ModelError(f"object {i}: delay out of range")
        if cat != "shelf" and len(pts) > 1 and speed <= 0: raise ModelError(f"object {i}: moving object needs speed > 0")
        curve = o.get("curve", "straight")
        if curve not in ("straight", "smooth"): raise ModelError(f"object {i}: curve must be straight|smooth")
        out.append({"category": cat, "waypoints": pts, "speed": speed, "radius": radius, "delay": delay,
                    "curve": curve,
                    "mode": o.get("mode") if o.get("mode") in ("stop", "loop", "pingpong") else "stop"})
    return {"name": str(obj.get("name", "muse-generated-scene"))[:64],
            "explanation": str(obj.get("explanation", ""))[:600], "objects": out}

def scene_quality(objects: list) -> dict:
    """Deterministic quality gate for generated scenes: is there a real
    interaction worth analysing, does anything drive through a shelf, and
    are the turns physically plausible? Computed with the same engine
    users' analyses run on — the model gets scored, not trusted."""
    from engine.curves import Path, sample_tracks
    issues, warnings = [], []
    objs = [dict(o, object_id=f"{o['category']}-{i+1}") for i, o in enumerate(objects)]
    shelves = [o for o in objs if o["category"] == "shelf"]
    for o in objs:
        path = Path(o["waypoints"], o.get("curve", "straight"), closed=(o.get("mode") == "loop"))
        warnings += [f"{o['object_id']}: {w}" for w in path.realism(o["category"])["warnings"]]
        if o["category"] != "shelf":
            for s in shelves:
                sc = s["waypoints"][0]
                if any((q.x - sc[0]) ** 2 + (q.y - sc[1]) ** 2 < (s["radius"] + o["radius"] * 0.5) ** 2 for q in path.points):
                    issues.append(f"{o['object_id']} path passes through the {s['object_id']} footprint")
    min_sep = None
    try:
        tracks = sample_tracks(objs)
        moving = [tr for tr in tracks if len(tr.points) > 1]
        for i, a in enumerate(moving):
            for b in moving[i + 1:]:
                n = min(len(a.points), len(b.points))
                d = min(a.points[k][1].dist(b.points[k][1]) - a.radius - b.radius for k in range(n))
                min_sep = d if min_sep is None else min(min_sep, d)
    except Exception as e:
        issues.append(f"scene could not be sampled: {e}")
    if min_sep is not None and min_sep > 2.0:
        issues.append(f"no close interaction: closest surface separation is {min_sep:.2f} m (aim for < 2 m)")
    return {"min_separation_m": None if min_sep is None else round(min_sep, 3),
            "has_close_interaction": bool(min_sep is not None and min_sep <= 2.0),
            "issues": issues, "warnings": warnings}

def generate_scene(description: str) -> tuple[dict, dict]:
    """Muse Spark generates a Create Lab scene as strict JSON (validated)."""
    if not description or len(description) > 4000:
        raise ValueError(f"scene description must be 1..4000 characters (yours: {len(description)})")
    prompt = ("You design scenes for a physical-AI safety workbench. Stage: 16 x 14 metres, "
              "x right, y up, origin bottom-left. Reply with ONLY a JSON object: "
              '{"name": str, "explanation": str (one sentence), "objects": [{"category": one of '
              "forklift|pedestrian|robot|vehicle|cyclist|shelf, \"waypoints\": [[x,y],...] (1 point = static, "
              '2+ = path), "speed": number m/s (0 only for shelf), "radius": number m, "delay": number s, '
              '"mode": "stop"|"loop"|"pingpong", "curve": "straight"|"smooth"}]}. '
              "PATH DESIGN RULES (follow all): (1) Use \"smooth\" for anything that turns, crosses, "
              "approaches or patrols — with 3-5 waypoints so the curve is well defined; use \"straight\" "
              "only for aisle/road runs. (2) Keep every waypoint at least 1 m inside the stage. "
              "(3) Never route a moving path through a shelf waypoint's footprint. "
              "(4) Create ONE clear close interaction: two moving paths should pass within ~1 m of each "
              "other (surface to surface) so there is something to analyse. "
              "(5) Realistic speeds: forklift 1.2-1.8, pedestrian 1.1-1.6, robot 0.8-1.4, vehicle 2.0-3.0, "
              "cyclist 1.6-2.4 m/s. (6) A patrol that returns should use mode \"loop\" with a smooth curve. "
              "Do not claim any safety conclusion. Scene requested:\n" + description)
    feedback = ""
    for attempt in range(2):
        text, meta = _call(prompt + feedback, timeout=45, retries=1)
        try:
            obj = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except Exception as e:
            raise ModelError(f"model did not return JSON: {e}") from e
        scene = validate_scene(obj)
        quality = scene_quality(scene["objects"])
        scene["quality"] = quality
        meta = {**meta, "attempt": attempt + 1, "quality": quality}
        if not quality["issues"] or attempt == 1:
            return scene, meta
        feedback = ("\nYour previous attempt had these problems: " + "; ".join(quality["issues"])
                    + ". Fix exactly these while keeping the same scene concept.")
    return scene, meta

def narrate(findings: dict) -> tuple[str, dict]:
    prompt = ("Explain these deterministic physical-scene findings to an industrial engineer in "
              "under 130 words. Do not invent numbers, detections, or safety certifications; "
              "state assumptions and uncertainty plainly. Findings:\n" + json.dumps(findings)[:5000])
    return _call(prompt)
