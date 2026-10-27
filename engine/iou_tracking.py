"""Detection-to-track association by greedy IoU matching.

SAM image segmentation returns per-frame boxes with ids that are only stable
*within one response*. Across separately captured frames we therefore
re-associate detections ourselves: greedy highest-IoU matching with a
documented threshold, spawning new tracks for unmatched detections and
closing tracks that stop appearing. This is a deliberately simple,
fully deterministic tracker — its failure modes (identity switches under
heavy overlap) are exactly what engine.tracking.diagnostics reports."""
from __future__ import annotations
from .geometry import Vec
from .tracking import Track

def iou(a: dict, b: dict) -> float:
    x1, y1 = max(a["x1"], b["x1"]), max(a["y1"], b["y1"])
    x2, y2 = min(a["x2"], b["x2"]), min(a["y2"], b["y2"])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = lambda r: max(0.0, r["x2"] - r["x1"]) * max(0.0, r["y2"] - r["y1"])
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0

def _centre(box: dict) -> Vec:
    return Vec((box["x1"] + box["x2"]) / 2, (box["y1"] + box["y2"]) / 2)

def _radius(box: dict) -> float:
    return max(box["x2"] - box["x1"], box["y2"] - box["y1"]) / 2

def build_tracks(frames: list, category: str = "object", iou_threshold: float = 0.2,
                 space: str = "pixel") -> list:
    """frames: [{t, records: [{box:{x1,y1,x2,y2,...}, confidence}]}] time-ordered.
    Returns Tracks in `space` (pixel by default — detections are image-space;
    callers convert with calibration only when a valid scale exists)."""
    if not 0 < iou_threshold <= 1: raise ValueError("iou_threshold must be in (0,1]")
    frames = sorted(frames, key=lambda f: f["t"])
    open_tracks: list[dict] = []   # {last_box, points, category}
    finished: list[dict] = []
    counter = 0
    for frame in frames:
        t, records = float(frame["t"]), frame.get("records", [])
        candidates = []
        for ti, tr in enumerate(open_tracks):
            for ri, rec in enumerate(records):
                v = iou(tr["last_box"], rec["box"])
                if v >= iou_threshold: candidates.append((v, ti, ri))
        candidates.sort(reverse=True)
        used_t, used_r = set(), set()
        for _, ti, ri in candidates:
            if ti in used_t or ri in used_r: continue
            used_t.add(ti); used_r.add(ri)
            box = records[ri]["box"]
            open_tracks[ti]["points"].append((t, _centre(box)))
            open_tracks[ti]["last_box"] = box
            open_tracks[ti]["last_seen"] = t
        # close tracks not seen in this frame (kept simple & deterministic)
        still_open = []
        for ti, tr in enumerate(open_tracks):
            if ti in used_t or tr.get("last_seen") == t: still_open.append(tr)
            else: finished.append(tr)
        open_tracks = still_open
        for ri, rec in enumerate(records):
            if ri in used_r: continue
            counter += 1
            box = rec["box"]
            open_tracks.append({"points": [(t, _centre(box))], "last_box": box, "last_seen": t,
                                "radius": _radius(box), "name": f"{category}-{counter}"})
    finished.extend(open_tracks)
    tracks = []
    for tr in finished:
        if len(tr["points"]) < 1: continue
        tracks.append(Track(tr["name"], category, space,
                            [(round(t, 3), p) for t, p in tr["points"]],
                            round(tr.get("radius", 0.0), 3), "MODEL_DERIVED"))
    return sorted(tracks, key=lambda x: x.object_id)
