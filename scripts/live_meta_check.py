"""Live Meta Model API verification. Requires MODEL_API_KEY in environment.
Generates a synthetic test frame (pure-stdlib PNG), then runs:
  1. Muse Spark narration of deterministic findings
  2. Muse Spark structured hypothesis (schema-validated)
  3. SAM 3.1 segmentation of the synthetic frame (one concept per request)
Records everything (except the key) as JSON on stdout for docs/LIVE_META_VERIFICATION.md.
Synthetic shapes may legitimately yield zero SAM matches — that is a valid,
documented outcome and is recorded as-is, never embellished."""
import base64, hashlib, json, struct, sys, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.meta import spark, sam

def make_png(w=640, h=480) -> bytes:
    img = bytearray(w * h * 3)
    def rect(x0, y0, x1, y1, rgb):
        for y in range(y0, y1):
            for x in range(x0, x1):
                i = (y * w + x) * 3; img[i:i + 3] = bytes(rgb)
    for i in range(0, len(img), 3): img[i:i + 3] = bytes((16, 20, 28))       # background
    rect(80, 300, 220, 380, (56, 198, 217))                                 # "forklift" body block
    rect(180, 240, 220, 300, (56, 198, 217))
    rect(430, 180, 470, 330, (242, 176, 74))                                # "person" block
    raw = b"".join(b"\x00" + bytes(img[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

def main() -> int:
    out = {"spark_model": spark.MODEL, "sam_model": sam.MODEL, "configured": spark.configured()}
    if not spark.configured():
        print(json.dumps({**out, "status": "BLOCKED_CREDENTIALS"}, indent=2)); return 2
    findings = {"scenario": "warehouse-near-miss (synthetic fixture)",
                "pair_event": {"type": "near_miss", "d_min_m": 0.42, "ttc_s": None},
                "engine": "deterministic CPA/TTC, calibrated 0.05 m/px"}
    try:
        text, meta = spark.narrate(findings)
        out["spark_narrate"] = {"ok": True, "meta": meta, "text": text[:600]}
    except Exception as e:
        out["spark_narrate"] = {"ok": False, "error": str(e)[:400]}
    try:
        obj, meta = spark.propose_hypothesis(findings)
        out["spark_hypothesis"] = {"ok": True, "meta": meta, "hypothesis": obj}
    except Exception as e:
        out["spark_hypothesis"] = {"ok": False, "error": str(e)[:400]}
    png = make_png()
    out["test_frame"] = {"bytes": len(png), "sha256": hashlib.sha256(png).hexdigest(),
                         "description": "synthetic 640x480 PNG: cyan forklift-like block, amber person-like block"}
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    for concept in ("person", "forklift"):
        try:
            r = sam.segment_image(url, concept)
            out[f"sam_{concept}"] = {"ok": True, "model": r["model"], "http_status": r["http_status"],
                                     "latency_ms": r["latency_ms"], "objects": r["objects"],
                                     "frames": len(r["frames"]), "diagnostics": r["diagnostics"][:3],
                                     "first_records": (r["frames"][0]["records"][:2] if r["frames"] else [])}
        except Exception as e:
            out[f"sam_{concept}"] = {"ok": False, "error": str(e)[:400]}
    print(json.dumps(out, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
