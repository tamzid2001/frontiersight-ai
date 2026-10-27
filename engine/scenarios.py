"""Synthetic demonstration scenarios with KNOWN ground truth.

Ground truth (analytic trajectories) is stored separately from the
'observations' the analysis pipeline consumes, so evaluation is never circular:
observations are sampled (and, for the occlusion scenario, deliberately
withheld) from ground truth by this generator with a fixed seed."""
from __future__ import annotations
import json, math
from pathlib import Path
from .geometry import Vec
from .tracking import Track

DT = 0.1
DURATION = 8.0

def _sample(fn, t_end=DURATION, omit=None):
    pts, t = [], 0.0
    while t <= t_end + 1e-9:
        if not (omit and omit[0] <= t <= omit[1]): pts.append((round(t, 3), fn(t)))
        t = round(t + DT, 10)
    return pts

def build(name: str) -> dict:
    if name == "warehouse-near-miss":
        gt = {"forklift-1": ("forklift", lambda t: Vec(1.0 + 1.6 * t, 5.0), 0.9),
              "pedestrian-1": ("pedestrian", lambda t: Vec(8.6, 12.0 - 1.55 * t), 0.45)}
        cal, desc = {"metres_per_pixel": 0.05, "frame": "warehouse floor plan (synthetic)"}, \
            "Forklift travels east at 1.6 m/s; pedestrian crosses south at 1.55 m/s. Paths converge mid-aisle."
        occl = {}
    elif name == "safe-passing":
        gt = {"forklift-1": ("forklift", lambda t: Vec(1.0 + 1.4 * t, 4.0), 0.9),
              "pedestrian-1": ("pedestrian", lambda t: Vec(12.0 - 1.2 * t, 9.5), 0.45)}
        cal, desc = {"metres_per_pixel": 0.05, "frame": "warehouse floor plan (synthetic)"}, \
            "Forklift and pedestrian pass on parallel lanes with >5 m separation throughout."
        occl = {}
    elif name == "occlusion-uncertainty":
        gt = {"forklift-1": ("forklift", lambda t: Vec(1.0 + 1.2 * t, 6.0), 0.9),
              "pedestrian-1": ("pedestrian", lambda t: Vec(7.5, 11.0 - 1.1 * t), 0.45)}
        cal, desc = {"metres_per_pixel": 0.05, "frame": "warehouse floor plan (synthetic)"}, \
            "Pedestrian is occluded behind shelving from t=3.0s to t=4.5s; identity and motion are uncertain across the gap."
        occl = {"pedestrian-1": (3.0, 4.5)}
    else:
        raise KeyError(name)
    tracks, ground_truth = [], {}
    for oid, (cat, fn, radius) in gt.items():
        omit = occl.get(oid)
        tracks.append(Track(oid, cat, "world", _sample(fn, omit=omit), radius, "FIXTURE", [omit] if omit else []))
        ground_truth[oid] = {"category": cat, "radius": radius,
                             "analytic": "linear constant-velocity (see engine/scenarios.py)",
                             "occluded_window": omit}
    return {"id": name, "description": desc, "kind": "SYNTHETIC_FIXTURE",
            "calibration": cal, "tracks": tracks, "ground_truth": ground_truth,
            "disclaimer": "Synthetic fixture with known ground truth. Results validate the analysis pipeline on synthetic data only — not performance on real industrial video."}

SCENARIOS = ["warehouse-near-miss", "safe-passing", "occlusion-uncertainty"]

def track_to_dict(tr: Track) -> dict:
    return {"object_id": tr.object_id, "category": tr.category, "space": tr.space, "radius": tr.radius,
            "source": tr.source, "occluded": tr.occluded,
            "points": [[t, round(p.x, 4), round(p.y, 4)] for t, p in tr.points]}

def scenario_to_dict(sc: dict) -> dict:
    return {"id": sc["id"], "description": sc["description"], "kind": sc["kind"],
            "calibration": sc["calibration"], "disclaimer": sc["disclaimer"],
            "tracks": [track_to_dict(t) for t in sc["tracks"]], "ground_truth": sc["ground_truth"]}

def export_fixtures(out_dir: str) -> list:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); written = []
    for name in SCENARIOS:
        p = out / f"{name}.json"; p.write_text(json.dumps(scenario_to_dict(build(name)), indent=1)); written.append(str(p))
    return written
