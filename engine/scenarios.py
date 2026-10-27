"""Synthetic demonstration scenarios with KNOWN ground truth.

Ground truth (the path definitions: waypoints, curve type, speed) is stored
separately from the 'observations' the analysis pipeline consumes, so
evaluation is never circular: observations are sampled from ground-truth
paths at 10 Hz (and, for the occlusion scenario, deliberately withheld
across the occlusion window).

Motion is defined the same way users define it in Create Lab: waypoints +
straight-or-smooth (Catmull-Rom) paths, arc-length parameterised by
engine/curves.py, so speeds are physically consistent along curves.
Straight warehouse aisles stay straight; crossings, turns and patrols curve."""
from __future__ import annotations
import json
from pathlib import Path as FilePath
from .curves import Path
from .tracking import Track

DT = 0.1
DURATION = 8.0

# oid -> (category, waypoints, speed m/s, radius m, curve, mode)
SPECS: dict[str, dict] = {
    "warehouse-near-miss": {
        "desc": "Forklift travels the aisle east at 1.6 m/s; a pedestrian crosses south on a curved path. Their paths converge mid-aisle.",
        "actors": {
            "forklift-1": ("forklift", [[1.0, 5.0], [13.0, 5.0]], 1.6, 0.9, "straight", "stop"),
            "pedestrian-1": ("pedestrian", [[8.6, 12.5], [8.0, 9.0], [8.5, 5.5], [9.2, 1.0]], 1.55, 0.45, "smooth", "stop"),
        }, "occl": {}},
    "safe-passing": {
        "desc": "Forklift and pedestrian travel gently curved parallel lanes with >5 m separation throughout.",
        "actors": {
            "forklift-1": ("forklift", [[1.0, 4.0], [7.0, 3.6], [13.0, 4.2]], 1.4, 0.9, "smooth", "stop"),
            "pedestrian-1": ("pedestrian", [[12.0, 9.5], [7.0, 9.9], [1.0, 9.3]], 1.2, 0.45, "smooth", "stop"),
        }, "occl": {}},
    "occlusion-uncertainty": {
        "desc": "A pedestrian on a curved crossing path is occluded behind shelving from t=3.0s to t=4.5s; identity and motion are uncertain across the gap.",
        "actors": {
            "forklift-1": ("forklift", [[1.0, 6.0], [13.0, 6.0]], 1.2, 0.9, "straight", "stop"),
            "pedestrian-1": ("pedestrian", [[7.5, 11.0], [6.8, 8.0], [7.6, 4.0], [8.2, 0.8]], 1.1, 0.45, "smooth", "stop"),
        }, "occl": {"pedestrian-1": (3.0, 4.5)}},
    "warehouse-multi": {
        "desc": "Five-entity warehouse: two forklifts, a pedestrian on a curved crossing, a robot on a smooth patrol loop, and a static shelf row. Multiple pairs converge.",
        "actors": {
            "forklift-1": ("forklift", [[1.0, 5.0], [13.0, 5.0]], 1.6, 0.9, "straight", "stop"),
            "pedestrian-1": ("pedestrian", [[8.6, 12.5], [8.0, 9.0], [8.5, 5.5], [9.2, 1.0]], 1.55, 0.45, "smooth", "stop"),
            "robot-1": ("robot", [[13.5, 3.2], [9.0, 1.4], [4.0, 2.2], [3.0, 5.5], [8.0, 6.4]], 1.1, 0.55, "smooth", "loop"),
            "forklift-2": ("forklift", [[2.0, 10.5], [7.0, 11.3], [12.5, 10.2]], 0.9, 0.9, "smooth", "stop"),
            "shelf-row": ("shelf", [[11.0, 7.0]], 0.0, 1.1, "straight", "stop"),
        }, "occl": {}},
    "intersection-crossing": {
        "desc": "A vehicle turns through a synthetic intersection on a curved path while a cyclist and two pedestrians cross on curved paths — several closing pairs.",
        "actors": {
            "vehicle-1": ("vehicle", [[0.5, 6.5], [6.0, 6.2], [10.0, 7.5], [13.0, 10.5]], 2.2, 1.1, "smooth", "stop"),
            "cyclist-1": ("cyclist", [[9.0, 12.5], [8.6, 8.0], [9.2, 3.0], [9.5, 0.5]], 1.9, 0.5, "smooth", "stop"),
            "pedestrian-1": ("pedestrian", [[12.5, 5.6], [9.0, 5.2], [5.0, 6.0], [1.5, 5.4]], 1.3, 0.45, "smooth", "stop"),
            "pedestrian-2": ("pedestrian", [[4.0, 1.0], [7.0, 1.6], [11.0, 1.2]], 0.8, 0.45, "smooth", "stop"),
        }, "occl": {}},
}

def _sample(path: Path, speed: float, mode: str, omit=None):
    pts, t = [], 0.0
    while t <= DURATION + 1e-9:
        if not (omit and omit[0] <= t <= omit[1]):
            pts.append((round(t, 3), path.position_at_time(t, speed, 0.0, mode)))
        t = round(t + DT, 10)
    return pts

def build(name: str) -> dict:
    if name not in SPECS: raise KeyError(name)
    spec = SPECS[name]
    tracks, ground_truth = [], {}
    for oid, (cat, wps, speed, radius, curve, mode) in spec["actors"].items():
        path = Path(wps, curve, closed=(mode == "loop"))
        omit = spec["occl"].get(oid)
        tracks.append(Track(oid, cat, "world", _sample(path, speed, mode, omit),
                            radius, "FIXTURE", [omit] if omit else []))
        ground_truth[oid] = {"category": cat, "radius": radius, "waypoints": wps,
                             "curve": curve, "mode": mode, "speed_m_s": speed,
                             "analytic": "Catmull-Rom spline through waypoints, arc-length parameterised (engine/curves.py)"
                                         if curve == "smooth" else "straight polyline through waypoints, arc-length parameterised",
                             "occluded_window": list(omit) if omit else None}
    return {"id": name, "description": spec["desc"], "kind": "SYNTHETIC_FIXTURE",
            "calibration": {"metres_per_pixel": 0.05, "frame": "floor plan (synthetic)"},
            "tracks": tracks, "ground_truth": ground_truth,
            "disclaimer": "Synthetic fixture with known ground truth (path definitions held separately). Results validate the analysis pipeline on synthetic data only — not performance on real industrial video."}

SCENARIOS = list(SPECS)

def track_to_dict(tr: Track) -> dict:
    return {"object_id": tr.object_id, "category": tr.category, "space": tr.space, "radius": tr.radius,
            "source": tr.source, "occluded": tr.occluded,
            "points": [[t, round(p.x, 4), round(p.y, 4)] for t, p in tr.points]}

def scenario_to_dict(sc: dict) -> dict:
    return {"id": sc["id"], "description": sc["description"], "kind": sc["kind"],
            "calibration": sc["calibration"], "disclaimer": sc["disclaimer"],
            "tracks": [track_to_dict(t) for t in sc["tracks"]], "ground_truth": sc["ground_truth"]}

def export_fixtures(out_dir: str) -> list:
    out = FilePath(out_dir); out.mkdir(parents=True, exist_ok=True); written = []
    for name in SCENARIOS:
        p = out / f"{name}.json"; p.write_text(json.dumps(scenario_to_dict(build(name)), indent=1)); written.append(str(p))
    return written
