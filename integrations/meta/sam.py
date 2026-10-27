"""SAM 3.1 via Meta Model API + parser for the documented output grammar.

Wire format (dev.meta.ai/docs/sam/reading-segmentation): segmentation arrives
as special-token text on the Responses `output_text` lane, one line per frame:
  <Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=W;h=H[;c=conf]|><|mask;x=0;y=0[;c=..];data=H,W,<enc>payload|>,...
Object ids are stable within a response; masks are base85 payloads whose full
raster decoding is delegated to Meta's `meta-sam-parser` package when installed
(we parse boxes, ids, confidences, and mask headers here, and record mask
payloads opaquely — we never fabricate a raster we did not decode)."""
from __future__ import annotations
import json, os, re, time, urllib.request, urllib.error, uuid
from .spark import BlockedCredentials, ModelError, BASE

MODEL = os.environ.get("META_SAM_MODEL", "sam-3.1")
LINE = re.compile(r"<(\d+)f>(.*)")
RECORD = re.compile(r"(\d+)<\|box;([^|]*)\|>(?:<\|mask;([^|]*)\|>)?")

def _fields(s: str) -> dict:
    out = {}
    for part in s.split(";"):
        if "=" in part:
            k, v = part.split("=", 1); out[k] = v
    return out

def parse_output_text(text: str) -> list:
    """Parse SAM special-token text into frame records. Malformed records are
    collected as diagnostics, mirroring Meta's parser contract (never crash,
    never invent)."""
    frames, diagnostics = [], []
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m:
            if line.strip(): diagnostics.append({"severity": "warning", "code": "unparsed_line", "raw": line[:120]})
            continue
        frame_idx, rest = int(m.group(1)), m.group(2)
        records = []
        for rm in RECORD.finditer(rest):
            box = _fields(rm.group(2))
            try:
                rec = {"object_id": int(rm.group(1)),
                       "box": {"x1": int(box["x1"]), "y1": int(box["y1"]), "x2": int(box["x2"]), "y2": int(box["y2"]),
                               "frame_w": int(box["w"]), "frame_h": int(box["h"])},
                       "confidence": float(box["c"]) if "c" in box else None}
            except (KeyError, ValueError) as e:
                diagnostics.append({"severity": "error", "code": "malformed_record", "raw": rm.group(0)[:120], "detail": str(e)})
                continue
            if rm.group(3):
                mask = _fields(rm.group(3))
                data = mask.get("data", "")
                rec["mask"] = {"origin": [int(mask.get("x", 0)), int(mask.get("y", 0))],
                               "confidence": float(mask["c"]) if "c" in mask else None,
                               "raster": data.split(",", 2)[:2], "encoding": data.split(",", 2)[2][:1] if "," in data else None,
                               "payload_chars": max(0, len(data.split(",", 2)[2]) - 1) if data.count(",") >= 2 else 0,
                               "decoded": False,
                               "note": "payload retained opaquely; decode with meta-sam-parser decode_mask_to_raster"}
            records.append(rec)
        frames.append({"frame": frame_idx, "records": records})
    return {"frames": frames, "diagnostics": diagnostics,
            "objects": sorted({r["object_id"] for f in frames for r in f["records"]})}

def segment_image(image_data_url: str, concept: str, timeout: int = 90) -> dict:
    """One concept per request (documented constraint). Image as data URL."""
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    if not concept or any(ch in concept for ch in ",;+\n"): raise ValueError("concept must be one short noun phrase")
    payload = {"model": MODEL, "stream": True,
               "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
               "input": [{"type": "message", "role": "user", "content": [
                   {"type": "input_text", "text": concept},
                   {"type": "input_image", "image_url": image_data_url}]}]}
    req = urllib.request.Request(BASE + "/responses", data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Request-Id": str(uuid.uuid4())})
    started, text_parts, status = time.time(), [], None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            for raw in r:
                line = raw.decode(errors="ignore").strip()
                if line.startswith("data:"):
                    try: ev = json.loads(line[5:])
                    except Exception: continue
                    if ev.get("type") == "response.output_text.delta": text_parts.append(ev.get("delta", ""))
                    elif ev.get("type") == "response.output_text.done": text_parts = [ev.get("text", "".join(text_parts))]
    except urllib.error.HTTPError as e:
        raise ModelError(f"SAM HTTP {e.code}: {e.read().decode()[:300]}") from e
    text = "".join(text_parts)
    parsed = parse_output_text(text)
    parsed.update({"model": MODEL, "concept": concept, "http_status": status,
                   "latency_ms": round((time.time() - started) * 1000), "raw_output_chars": len(text)})
    return parsed
