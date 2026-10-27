"""Muse Image — illustrative concept visuals ONLY. Generated imagery is never
evidence and never substitutes for verified simulation or observed video."""
from __future__ import annotations
import json, os, urllib.request, urllib.error
from .spark import BlockedCredentials, BASE

MODEL = os.environ.get("META_IMAGE_MODEL", "muse-image-1.0")

def generate_illustration(prompt: str, timeout: int = 90) -> dict:
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    req = urllib.request.Request(BASE + "/images/generations", method="POST",
        data=json.dumps({"model": MODEL, "prompt": prompt}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Muse Image HTTP {e.code}: {e.read().decode()[:300]}") from e
    out["label"] = "ILLUSTRATIVE — generated imagery, not evidence"
    out["model"] = MODEL
    return out
