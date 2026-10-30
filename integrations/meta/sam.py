"""SAM 3.1 via Meta Model API + parser for the documented output grammar.

Wire format (dev.meta.ai/docs/sam/reading-segmentation): segmentation arrives
as special-token text on the Responses `output_text` lane, one line per frame:
  <Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=W;h=H[;c=conf]|><|mask;x=0;y=0[;c=..];data=H,W,<enc>payload|>,...
Object ids are stable within a response; masks are base85 payloads whose full
raster decoding is delegated to Meta's `meta-sam-parser` package when installed
(we parse boxes, ids, confidences, and mask headers here, and record mask
payloads opaquely — we never fabricate a raster we did not decode)."""
from __future__ import annotations
from .credentials import api_key
import base64, json, math, os, re, struct, time, urllib.request, urllib.error, uuid, zlib
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

def _mask_png(raster: bytes, width: int, height: int) -> str:
    """Encode a bounded binary raster as a real white/alpha PNG, no guessed mask."""
    if len(raster) != width * height or any(value not in (0, 1) for value in raster):
        raise ValueError("invalid binary mask raster")
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\0" + bytes(channel for pixel in raster[y*width:(y+1)*width]
                       for channel in (255, pixel * 255)) for y in range(height))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 4, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _decode_complete_mask(payload: str, width: int, height: int) -> bytes:
    from meta_sam_parser import SegmentationMask, decode_mask_to_raster, InvalidSegmentationMaskError
    try:
        return decode_mask_to_raster(SegmentationMask(
            encoding="one_bit" if payload[0] == "!" else "lossless", payload=payload,
            width=width, height=height))
    except InvalidSegmentationMaskError:
        raise ValueError("invalid encoded mask") from None


def parse_output_text(text: str, *, decode_masks: bool = False) -> dict:
    """Parse SAM special-token text into frame records. Malformed records are
    collected as diagnostics, mirroring Meta's parser contract (never crash,
    never invent)."""
    if not isinstance(text, str) or len(text) > 8 * 1024 * 1024:
        raise ValueError("segmentation output budget exceeded")
    frames, diagnostics, decoded_pixels = [], [], 0
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
                b = rec["box"]
                if (not 0 < b["frame_w"] <= 16384 or not 0 < b["frame_h"] <= 16384
                    or not 0 <= b["x1"] <= b["x2"] <= b["frame_w"]
                    or not 0 <= b["y1"] <= b["y2"] <= b["frame_h"]
                    or rec["confidence"] is not None and (not math.isfinite(rec["confidence"]) or not 0 <= rec["confidence"] <= 1)):
                    raise ValueError("invalid source box or confidence")
            except (KeyError, ValueError) as e:
                diagnostics.append({"severity": "error", "code": "malformed_record", "raw": rm.group(0)[:120], "detail": str(e)})
                continue
            if rm.group(3):
                mask = _fields(rm.group(3))
                data = mask.get("data", "")
                rec["mask"] = {"origin": [0, 0],
                               "raster": data.split(",", 2)[:2], "encoding": data.split(",", 2)[2][:1] if "," in data else None,
                               "payload_chars": max(0, len(data.split(",", 2)[2]) - 1) if data.count(",") >= 2 else 0,
                               "decoded": False,
                               "note": "payload retained opaquely; decode with meta-sam-parser decode_mask_to_raster"}
                if decode_masks:
                    try:
                        height, width, payload = data.split(",", 2)
                        width, height = int(width), int(height)
                        if not (0 < width <= 16384 and 0 < height <= 16384 and width * height <= 1_000_000) or decoded_pixels + width * height > 4_000_000:
                            raise ValueError("mask pixel budget exceeded")
                        if int(mask.get("x", 0)) != 0 or int(mask.get("y", 0)) != 0 or not payload.startswith(("!", "~")):
                            raise ValueError("unsupported mask origin or encoding")
                        raster = _decode_complete_mask(payload, width, height)
                        decoded_pixels += width * height
                        rec["mask"].update(decoded=True, width=width, height=height,
                            png_data_url=_mask_png(raster, width, height), note="Decoded by the official Meta SAM parser; box-local raster.")
                    except (ValueError, ImportError):
                        diagnostics.append({"severity": "warning", "code": "mask_not_decoded", "object_id": rec["object_id"]})
            records.append(rec)
            if len(records) >= 48:
                diagnostics.append({"severity": "warning", "code": "frame_record_limit"})
                break
        frames.append({"frame": frame_idx, "records": records})
        if len(frames) >= 512:
            diagnostics.append({"severity": "warning", "code": "frame_limit"})
            break
    return {"frames": frames, "diagnostics": diagnostics,
            "objects": sorted({r["object_id"] for f in frames for r in f["records"]})}

def segment_video(video_ref: str, concept: str, is_file_id: bool = False, timeout: int = 300) -> dict:
    """SAM 3.1 video segmentation/tracking (documented input_video part).
    Researcher-gated at the API layer; this function performs the call and
    parses frames with the same documented-grammar parser as images."""
    key = api_key()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    if not concept or any(ch in concept for ch in ",;+\n"): raise ValueError("concept must be one short noun phrase")
    media = {"type": "input_video", "file_id": video_ref} if is_file_id else {"type": "input_video", "video_url": video_ref}
    payload = {"model": MODEL, "stream": True,
               "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
               "input": [{"type": "message", "role": "user", "content": [
                   {"type": "input_text", "text": concept}, media]}]}
    req = urllib.request.Request(BASE + "/responses", data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Request-Id": str(uuid.uuid4())})
    started, text_parts = time.time(), []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            for raw in r:
                line = raw.decode(errors="ignore").strip()
                if line.startswith("data:"):
                    try: ev = json.loads(line[5:])
                    except Exception: continue
                    if ev.get("type") == "response.output_text.delta": text_parts.append(ev.get("delta", ""))
    except urllib.error.HTTPError as e:
        raise ModelError(f"SAM video HTTP {e.code}; provider details withheld") from None
    text = "".join(text_parts)
    parsed = parse_output_text(text)
    parsed.update({"model": MODEL, "concept": concept, "http_status": status,
                   "latency_ms": round((time.time() - started) * 1000), "raw_output_chars": len(text)})
    return parsed

def segment_image(image_data_url: str, concept: str, timeout: int = 50) -> dict:
    """One concept per request (documented constraint). Image as data URL."""
    key = api_key()
    if not key: raise BlockedCredentials("BLOCKED_CREDENTIALS: MODEL_API_KEY not set (server-side only)")
    if not isinstance(concept, str) or not 1 <= len(concept) <= 100 or any(ch in concept for ch in ",;+\n"): raise ValueError("concept must be one short noun phrase")
    if not isinstance(image_data_url, str) or len(image_data_url) > 3_500_000 or not re.match(r"^data:image/(jpeg|png);base64,", image_data_url):
        raise ValueError("image must be a bounded JPEG or PNG data URL")
    try:
        raw_image = base64.b64decode(image_data_url.split(",", 1)[1], validate=True)
        signature = b"\x89PNG\r\n\x1a\n" if image_data_url.startswith("data:image/png;") else b"\xff\xd8"
        if not raw_image.startswith(signature):
            raise ValueError("invalid image signature")
    except (ValueError, base64.binascii.Error):
        raise ValueError("invalid image data") from None
    payload = {"model": MODEL, "stream": True,
               "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
               "input": [{"type": "message", "role": "user", "content": [
                   {"type": "input_text", "text": concept},
                   {"type": "input_image", "image_url": image_data_url}]}]}
    req = urllib.request.Request(BASE + "/responses", data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Request-Id": str(uuid.uuid4())})
    started, text_parts, status, completed, size = time.time(), [], None, False, 0
    deadline = time.monotonic() + min(timeout, 50)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            while True:
                raw = r.readline(8 * 1024 * 1024 + 1)
                if not raw: break
                if len(raw) > 8 * 1024 * 1024 or time.monotonic() > deadline:
                    raise ModelError("SAM stream exceeded its size or time budget")
                line = raw.decode(errors="ignore").strip()
                if line.startswith("data:"):
                    try: ev = json.loads(line[5:])
                    except (ValueError, TypeError): continue
                    if not isinstance(ev, dict): continue
                    if ev.get("type") == "response.output_text.delta":
                        delta = ev.get("delta", "")
                        if not isinstance(delta, str): raise ModelError("Invalid SAM output")
                        size += len(delta)
                        if size > 8 * 1024 * 1024: raise ModelError("SAM output exceeded its budget")
                        text_parts.append(delta)
                    elif ev.get("type") == "response.output_text.done": text_parts = [ev.get("text", "".join(text_parts))]
                    elif ev.get("type") == "response.completed":
                        completed = True
                        break
                    elif ev.get("type") in ("response.failed", "response.incomplete", "error"):
                        raise ModelError("SAM did not complete the image segmentation")
    except urllib.error.HTTPError as e:
        raise ModelError(f"SAM HTTP {e.code}; provider details withheld") from None
    text = "".join(text_parts)
    if not completed: raise ModelError("SAM stream ended without completion")
    parsed = parse_output_text(text, decode_masks=True)
    parsed.update({"model": MODEL, "concept": concept, "http_status": status,
                   "latency_ms": round((time.time() - started) * 1000), "raw_output_chars": len(text)})
    return parsed
