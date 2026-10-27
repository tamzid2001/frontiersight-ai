"""Scene-level kinematics: pairwise proximity events, calibration gating.

Calibration rule (hard): metric (metre/second) claims are produced ONLY when a
valid scale is declared. Pixel-space scenes return pixel quantities, set
`metric_claims=False`, and explain the ambiguity. Nothing is silently converted."""
from __future__ import annotations
import math
from dataclasses import dataclass
from .geometry import Vec, closest_approach, time_to_collision
from .tracking import Track

@dataclass(frozen=True)
class Calibration:
    metres_per_pixel: float | None   # None => uncalibrated (pixel space only)
    frame: str = "image"
    def validate(self):
        if self.metres_per_pixel is not None and not (math.isfinite(self.metres_per_pixel) and self.metres_per_pixel > 0):
            raise ValueError("invalid calibration: metres_per_pixel must be positive and finite")
    @property
    def calibrated(self) -> bool:
        return self.metres_per_pixel is not None

def to_world(track: Track, cal: Calibration) -> Track:
    cal.validate()
    if not cal.calibrated: raise ValueError("cannot convert to world space without calibration")
    if track.space == "world": return track
    s = cal.metres_per_pixel
    return Track(track.object_id, track.category, "world",
                 [(t, Vec(p.x * s, p.y * s)) for t, p in track.points],
                 track.radius * s, track.source, list(track.occluded))

def analyse_pair(a: Track, b: Track, cal: Calibration, horizon: float = 6.0,
                 near_miss_distance: float = 1.0) -> dict:
    """Proximity analysis over the overlapping observed window. Uses each track's
    latest finite-difference velocity at the window start (documented assumption)."""
    if a.space != b.space: raise ValueError("tracks must share a coordinate space")
    _units = "m" if a.space == "world" else "px"
    if len(a.points) < 2 or len(b.points) < 2:
        return {"pair": [a.object_id, b.object_id], "event": None, "space": a.space,
                "reason": "insufficient observations: a track has fewer than 2 points, so no velocity can be estimated",
                "d_min": None, "closing": False, "ttc_s": None, "units": _units,
                "metric_claims": a.space == "world", "window": None, "assumptions": []}
    t0 = max(a.points[0][0], b.points[0][0]); t1 = min(a.points[-1][0], b.points[-1][0])
    if t1 <= t0: return {"pair": [a.object_id, b.object_id], "event": None, "space": a.space,
                         "reason": "no overlapping observed window", "d_min": None,
                         "closing": False, "ttc_s": None, "units": _units,
                         "metric_claims": a.space == "world", "window": None, "assumptions": []}
    pa, pb = a.position_at(t0), b.position_at(t0)
    va = a.velocity_at(_nearest_index(a, t0)); vb = b.velocity_at(_nearest_index(b, t0))
    cpa = closest_approach(pa, va, pb, vb, horizon)
    ttc = time_to_collision(pa, va, pb, vb, a.radius, b.radius, horizon)
    # Measured proximity along the ACTUAL (possibly curved) trajectories:
    # sample both tracks over the shared window — no straight-line assumption.
    measured_d, measured_t, measured_contact = math.inf, t0, False
    _steps = max(1, int((t1 - t0) / 0.05))
    for _i in range(_steps + 1):
        _t = t0 + (t1 - t0) * _i / _steps
        _d = a.position_at(_t).dist(b.position_at(_t))
        if _d < measured_d: measured_d, measured_t = _d, _t
        if _d <= a.radius + b.radius: measured_contact = True
    # Metric claims derive ONLY from the track space. A calibration object does
    # not convert coordinates by itself (use to_world first); pixel tracks with
    # a declared calibration are reported in px until converted.
    units = _units
    event = None
    if measured_contact:
        event = {"type": "contact_in_window", "d_min": round(measured_d, 4), "units": units,
                 "at_time_s": round(measured_t, 3)}
    elif ttc is not None:
        event = {"type": "predicted_contact", "ttc_s": round(ttc, 3), "at_time_s": round(t0 + ttc, 3)}
    elif cpa.closing and min(cpa.d_min, measured_d) < near_miss_distance:
        event = {"type": "near_miss", "d_min": round(min(cpa.d_min, measured_d), 4), "units": units,
                 "t_star_s": round(measured_t, 3)}
    return {"pair": [a.object_id, b.object_id], "space": a.space, "units": units,
            "metric_claims": a.space == "world",
            "window": [t0, t1], "d_min": round(cpa.d_min, 4), "closing": cpa.closing,
            "ttc_s": None if ttc is None else round(ttc, 3), "event": event,
            "measured": {"d_min": round(measured_d, 4), "t_at_d_min": round(measured_t, 3),
                         "contact": measured_contact,
                         "method": "sampled along actual trajectories at 50 ms over the shared window"},
            "assumptions": ["CPA/TTC: constant-velocity extrapolation over the stated horizon",
                            "measured_*: sampled along the actual (possibly curved) trajectories",
                            "finite-difference velocity at window start", f"near-miss threshold {near_miss_distance} {units}"]}

def _nearest_index(track: Track, t: float) -> int:
    idx = min(range(len(track.points)), key=lambda i: abs(track.points[i][0] - t))
    return max(1, idx)
