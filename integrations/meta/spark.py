"""Muse Spark via Meta Model API (Responses API, https://api.meta.ai/v1).

Used for: scene interpretation, hypothesis generation, and narrating
*independently computed* findings. Structured output is validated against a
local schema; invalid model JSON is rejected, never repaired into a claim.
The model must not invent detections, measurements, or verdicts — prompts say
so, and the engine never reads its numbers back as measurements."""
from __future__ import annotations
import json, os, time, urllib.request, urllib.error, uuid
from concurrent.futures import ThreadPoolExecutor, wait
from threading import BoundedSemaphore, Lock

BASE = os.environ.get("META_API_BASE", "https://api.meta.ai/v1")
MODEL = os.environ.get("META_MODEL", "muse-spark-1.3")

# Reasoning models served by Meta Model API (dev.meta.ai/docs/models).
# Muse Image / SAM 3.1 / Voice keep their dedicated models; Muse Spark Open
# and Muse Glimmer are self-hosted open weights and are NOT API-selectable.
MODELS = {
    "muse-spark-1.3": "Muse Spark 1.3 — latest Spark, balanced cost/quality (default)",
    "muse-spark-1.2": "Muse Spark 1.2",
    "muse-spark-1.1": "Muse Spark 1.1 — earliest Spark, cheapest Spark tier",
    "muse-spark-1.3-contributor": "Muse Spark 1.3 Contributor — discounted contributor mode",
    "muse-spark-1.2-contributor": "Muse Spark 1.2 Contributor — discounted contributor mode",
    "muse-wonder-1.0": "Muse Wonder 1.0 — most capable; complex reasoning, higher cost",
}

def resolve_model(requested: str | None) -> str:
    if not requested: return MODEL
    if requested not in MODELS:
        raise ValueError(f"unknown model '{requested}' — choose one of: {', '.join(MODELS)}")
    return requested

class BlockedCredentials(RuntimeError): pass
class ModelError(RuntimeError): pass
class SceneTimeout(ModelError): pass
class SceneBusy(ModelError): pass

# One bounded batch per process; a slow upstream cannot accumulate queued work.
SCENE_MAX_CANDIDATES = 8
SCENE_DEADLINE_SECONDS = 28
_SCENE_POOL = ThreadPoolExecutor(max_workers=SCENE_MAX_CANDIDATES, thread_name_prefix="scene")
_SCENE_CAPACITY = BoundedSemaphore(1)
MAX_MODEL_RESPONSE_BYTES = 1_048_576

def configured() -> bool:
    return bool(os.environ.get("MODEL_API_KEY", "").strip())

def _call(prompt: str, timeout: int = 60, retries: int = 2, model: str | None = None) -> tuple[str, dict]:
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    req_id = str(uuid.uuid4())
    body = json.dumps({"model": model or MODEL, "input": prompt}).encode()
    last = None
    for attempt in range(retries + 1):
        started = time.time()
        req = urllib.request.Request(BASE + "/responses", data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "X-Request-Id": req_id})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(MAX_MODEL_RESPONSE_BYTES + 1)
                if len(raw) > MAX_MODEL_RESPONSE_BYTES:
                    raise ModelError("Model response exceeded the size limit")
                out = json.loads(raw.decode())
            text = out.get("output_text") or ""
            if not text:
                for item in out.get("output", []):
                    for c in item.get("content", []):
                        if c.get("text"): text += c["text"]
            meta = {"model": model or MODEL, "request_id": req_id, "attempt": attempt,
                    "latency_ms": round((time.time() - started) * 1000),
                    "usage": out.get("usage"), "response_id": out.get("id"), "model_used": model or MODEL}
            return text, meta
        except urllib.error.HTTPError as e:
            last = ModelError(f"Meta Model API HTTP {e.code}")
            if e.code not in (429, 500, 502, 503) or attempt == retries: raise last
        except Exception as e:  # timeouts etc. — bounded retry, then surface
            last = e if isinstance(e, ModelError) else ModelError("Meta Model API request failed or timed out")
            if attempt == retries: raise last
        time.sleep(1.5 * (attempt + 1))
    raise last

HYPOTHESIS_SCHEMA = {"hypothesis": str, "intervention": dict, "rationale": str}

def propose_hypothesis(findings: dict, model: str | None = None) -> tuple[dict, dict]:
    """Ask Muse Spark for a counterfactual hypothesis as strict JSON.
    Returns (hypothesis, call_metadata). Raises ModelError on bad JSON/schema."""
    prompt = ("You are the Counterfactual Designer in a physical-AI safety research tool. "
              "Given these DETERMINISTIC findings (do not recompute or contradict them), propose ONE "
              "counterfactual intervention for the moving agent. Reply with ONLY a JSON object: "
              '{"hypothesis": str, "intervention": {"speed_reduction_pct": number 0-80, '
              '"intervention_time_s": number >= 0}, "rationale": str}. '
              "Findings:\n" + json.dumps(findings)[:5000])
    text, meta = _call(prompt, timeout=30, retries=1, model=resolve_model(model))
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
    if not isinstance(obj, dict):
        raise ModelError("scene must be a JSON object")
    objs = obj.get("objects")
    if not isinstance(objs, list) or not 2 <= len(objs) <= 8:
        raise ModelError("scene must contain 2..8 objects")
    out = []
    for i, o in enumerate(objs):
        if not isinstance(o, dict):
            raise ModelError(f"object {i}: must be a JSON object")
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

def generate_scene(description: str, model: str | None = None, candidates: int = 3) -> tuple[dict, dict]:
    """Generate a finite batch, select one valid scene, and never retry a candidate.

    All candidates share a wall-clock deadline. Cancellation stops client waiting;
    remote provider work may finish later. Capacity remains reserved until those
    requests finish, preventing timeout-triggered accumulation.
    """
    if isinstance(candidates, bool) or not isinstance(candidates, int) or not 1 <= candidates <= SCENE_MAX_CANDIDATES:
        raise ValueError(f"candidates must be an integer from 1 to {SCENE_MAX_CANDIDATES}")
    selected_model = resolve_model(model)
    if not description or len(description) > 4000:
        raise ValueError(f"scene description must be 1..4000 characters (yours: {len(description)})")
    if not configured():
        raise BlockedCredentials("MODEL_API_KEY not set (server-side only)")
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
    if not _SCENE_CAPACITY.acquire(blocking=False):
        raise SceneBusy("Scene generation is busy. Wait for the current batch to finish before trying again.")
    futures = []
    try:
        for _ in range(candidates):
            futures.append(_SCENE_POOL.submit(_call, prompt, timeout=20, retries=0, model=selected_model))
    except BaseException:
        # Executor shutdown can interrupt submission. Retain capacity for started work.
        if not futures:
            _SCENE_CAPACITY.release()
            raise
    remaining, lock = [len(futures)], Lock()
    def finished(_future):
        with lock:
            remaining[0] -= 1
            if remaining[0] == 0:
                _SCENE_CAPACITY.release()
    for future in futures:
        future.add_done_callback(finished)
    completed, pending = wait(futures, timeout=SCENE_DEADLINE_SECONDS)
    valid = []
    for index, future in enumerate(futures):
        if future not in completed:
            continue
        try:
            text, meta = future.result()
            obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
            scene = validate_scene(obj)
            quality = scene_quality(scene["objects"])
            scene["quality"] = quality
            # This is a geometry heuristic, not a learned or safety-certified rank.
            rank = (len(quality["issues"]), not quality["has_close_interaction"], index)
            valid.append((rank, scene, meta, index))
        except (ModelError, ValueError, TypeError, KeyError, OverflowError):
            continue
    if not valid:
        if pending:
            raise SceneTimeout("Scene-generation deadline reached. No scene was changed; retry manually.")
        raise ModelError("No candidate produced a valid scene. Try a clearer description; no automatic retry was made.")
    _, scene, meta, index = min(valid, key=lambda candidate: candidate[0])
    return scene, {**meta, "attempt": 1, "quality": scene["quality"],
                   "candidates_requested": candidates, "candidates_completed": len(completed),
                   "candidates_valid": len(valid), "selected_candidate": index + 1,
                   "deadline_seconds": SCENE_DEADLINE_SECONDS, "automatic_retries": 0}

def narrate(findings: dict) -> tuple[str, dict]:
    prompt = ("Explain these deterministic physical-scene findings to an industrial engineer in "
              "under 130 words. Do not invent numbers, detections, or safety certifications; "
              "state assumptions and uncertainty plainly. Findings:\n" + json.dumps(findings)[:5000])
    return _call(prompt)


# --- custom object generation: Spark designs a buildable spec, Muse Image renders it ---
OBJECT_SHAPES = {"box", "cylinder", "sphere", "capsule", "cone"}

def _hex(v, default):
    import re as _re
    return v if isinstance(v, str) and _re.fullmatch(r"#[0-9a-fA-F]{6}", v) else default

def validate_custom_object(obj: dict) -> dict:
    """A custom object is a small, bounded construction recipe (parts list)
    that both renderers (2D sprite fallback + Three.js) can build exactly.
    Anything outside the DSL is rejected, never improvised."""
    name = str(obj.get("name", "")).strip()
    if not 1 <= len(name) <= 40: raise ModelError("object name must be 1..40 characters")
    base = obj.get("base_category", "object")
    if base not in ("forklift", "pedestrian", "robot", "vehicle", "cyclist", "shelf", "object"):
        raise ModelError(f"unknown base_category: {base!r}")
    radius = float(obj.get("radius", 0.6)); height = float(obj.get("height_m", 1.2))
    if not 0.2 <= radius <= 2.5: raise ModelError("radius out of range [0.2, 2.5]")
    if not 0.3 <= height <= 3.5: raise ModelError("height_m out of range [0.3, 3.5]")
    pal_in = obj.get("palette") or {}
    palette = {"body": _hex(pal_in.get("body"), "#e9a13b"),
               "accent": _hex(pal_in.get("accent"), "#38c6d9"),
               "dark": _hex(pal_in.get("dark"), "#2c3444")}
    parts_in = obj.get("parts")
    if not isinstance(parts_in, list) or not 1 <= len(parts_in) <= 10:
        raise ModelError("parts must be a list of 1..10 construction parts")
    parts = []
    for i, part in enumerate(parts_in):
        shape = part.get("shape")
        if shape not in OBJECT_SHAPES: raise ModelError(f"part {i}: unknown shape {shape!r}")
        size = [float(x) for x in part.get("size", [])]
        pos = [float(x) for x in part.get("pos", [])]
        if len(size) != 3 or not all(0.05 <= x <= 3 for x in size):
            raise ModelError(f"part {i}: size must be [x,y,z] each in [0.05, 3] metres")
        if len(pos) != 3 or not (abs(pos[0]) <= 1.6 and 0 <= pos[1] <= 3.2 and abs(pos[2]) <= 1.6):
            raise ModelError(f"part {i}: pos must be [x,y,z] within the footprint, y in [0, 3.2]")
        color = part.get("color", "body")
        if color not in palette: color = _hex(color, palette["body"])
        parts.append({"shape": shape, "size": size, "pos": pos, "color": color})
    return {"name": name, "base_category": base, "radius": radius, "height_m": height,
            "palette": palette, "parts": parts,
            "description": str(obj.get("description", ""))[:240]}

def design_custom_object(description: str, model: str | None = None) -> tuple[dict, dict]:
    """Muse Spark designs a custom object as a strict, buildable spec."""
    if not description or len(description) > 300:
        raise ValueError(f"object description must be 1..300 characters (yours: {len(description)})")
    prompt = ("You design physical props for a 2D/3D scene editor. Reply with ONLY a JSON object: "
              '{"name": str (short, e.g. "Scissor Lift"), "description": str (one sentence), '
              '"base_category": one of forklift|pedestrian|robot|vehicle|cyclist|shelf|object '
              '(whose driving dynamics it inherits), "radius": number (footprint radius in metres, 0.2-2.5), '
              '"height_m": number (0.3-3.5), "palette": {"body": "#rrggbb", "accent": "#rrggbb", "dark": "#rrggbb"}, '
              '"parts": [{"shape": "box|cylinder|sphere|capsule|cone", "size": [x,y,z] metres, '
              '"pos": [x,y,z] centre offset in metres (y = height of the part centre, footprint centred on 0,0), '
              '"color": "body|accent|dark"}]}. '
              "Use 3-8 parts that genuinely read as the object from the side and from above: a scissor lift "
              "needs a base, criss-cross lift arms and a platform basket; a traffic barrier needs posts and a "
              "striped arm. Keep the total footprint honest. Object requested:\n" + description)
    text, meta = _call(prompt, timeout=20, retries=0, model=resolve_model(model))
    try:
        obj = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception as e:
        raise ModelError(f"model did not return JSON: {e}") from e
    return validate_custom_object(obj), meta

def procedural_object(description: str) -> dict:
    """Offline fallback object spec — labelled OFFLINE_PROCEDURAL, never a model call.
    Deterministic keyword design so the feature still works without a key."""
    d = description.lower()
    base, color = "object", "#9aa7b8"
    if any(k in d for k in ("lift", "platform", "scaffold")): base, color = "vehicle", "#f2b04a"
    elif any(k in d for k in ("barrier", "gate", "fence")): base, color = "shelf", "#e8e4da"
    elif any(k in d for k in ("robot", "bot", "drone")): base, color = "robot", "#aebfd2"
    elif any(k in d for k in ("car", "truck", "van", "vehicle")): base, color = "vehicle", "#4d8dff"
    elif any(k in d for k in ("person", "worker", "human")): base, color = "pedestrian", "#ff7847"
    spec = {"name": (description.strip()[:36] or "Custom object"),
            "description": "Procedurally generated offline from keywords (no model call was made).",
            "base_category": base, "radius": 0.8, "height_m": 1.6,
            "palette": {"body": color, "accent": "#38c6d9", "dark": "#2c3444"},
            "parts": [{"shape": "box", "size": [1.3, 0.8, 0.9], "pos": [0, 0.45, 0], "color": "body"},
                      {"shape": "cylinder", "size": [0.28, 0.5, 0.28], "pos": [0, 1.05, 0], "color": "accent"},
                      {"shape": "box", "size": [1.0, 0.22, 0.7], "pos": [0, 1.42, 0], "color": "dark"}]}
    return validate_custom_object(spec)
