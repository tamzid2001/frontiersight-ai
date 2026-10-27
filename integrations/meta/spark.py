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
    text, meta = _call(prompt)
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

def narrate(findings: dict) -> tuple[str, dict]:
    prompt = ("Explain these deterministic physical-scene findings to an industrial engineer in "
              "under 130 words. Do not invent numbers, detections, or safety certifications; "
              "state assumptions and uncertainty plainly. Findings:\n" + json.dumps(findings)[:5000])
    return _call(prompt)
