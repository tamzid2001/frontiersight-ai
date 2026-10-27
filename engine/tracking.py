"""Track normalisation, kinematics estimation, continuity diagnostics.

A Track is a list of (t, Vec) observations in ONE declared space ("pixel" or
"world"). Speeds/accelerations are finite differences over real timestamps;
irregular sampling is handled by using actual dt, never frame counts."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from .geometry import Vec

@dataclass
class Track:
    object_id: str
    category: str
    space: str                       # "pixel" | "world"
    points: list                     # list[(t: float, Vec)]
    radius: float = 0.0
    source: str = "FIXTURE"          # FIXTURE | MODEL_DERIVED | MANUAL
    occluded: list = field(default_factory=list)  # list[(t0, t1)] missing-evidence windows

    def __post_init__(self):
        if self.space not in ("pixel", "world"): raise ValueError(f"unknown space {self.space}")
        ts = [t for t, _ in self.points]
        if any(not math.isfinite(t) for t in ts): raise ValueError("non-finite timestamp")
        if ts != sorted(ts): raise ValueError("track timestamps must be time-ordered")
        if len(set(ts)) != len(ts): raise ValueError("duplicate timestamps in track")

    def velocity_at(self, i: int) -> Vec:
        if not 0 < i < len(self.points): raise IndexError(i)
        (t0, p0), (t1, p1) = self.points[i - 1], self.points[i]
        dt = t1 - t0
        if dt <= 0: raise ValueError("non-positive dt")
        return (p1 - p0).scale(1.0 / dt)

    def speeds(self) -> list:
        return [(self.points[i][0], self.velocity_at(i).norm()) for i in range(1, len(self.points))]

    def max_acceleration(self) -> float:
        vs = [(self.points[i][0], self.velocity_at(i)) for i in range(1, len(self.points))]
        acc = 0.0
        for (t0, v0), (t1, v1) in zip(vs, vs[1:]):
            if t1 > t0: acc = max(acc, (v1 - v0).norm() / (t1 - t0))
        return acc

    def position_at(self, t: float) -> Vec:
        """Piecewise-linear interpolation; raises outside the observed window
        rather than extrapolating silently."""
        if not self.points or t < self.points[0][0] or t > self.points[-1][0]:
            raise ValueError("t outside observed window (no silent extrapolation)")
        for (t0, p0), (t1, p1) in zip(self.points, self.points[1:]):
            if t0 <= t <= t1:
                k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                return p0 + (p1 - p0).scale(k)
        return self.points[-1][1]

def smooth(track: Track, window: int = 3) -> Track:
    """Centred moving-average smoothing. Documented assumption: biases peaks
    downward; used for display/estimation, ground truth is never overwritten."""
    if window < 3 or window % 2 == 0: raise ValueError("window must be odd and >= 3")
    half, pts = window // 2, track.points
    out = []
    for i, (t, _) in enumerate(pts):
        seg = [p for _, p in pts[max(0, i - half): i + half + 1]]
        out.append((t, Vec(sum(p.x for p in seg) / len(seg), sum(p.y for p in seg) / len(seg))))
    return Track(track.object_id, track.category, track.space, out, track.radius, track.source, list(track.occluded))

def diagnostics(track: Track, jump_threshold: float, max_plausible_accel: float) -> list:
    """Continuity diagnostics: teleport jumps (possible identity switches),
    implausible accelerations, and declared occlusion gaps."""
    out = []
    for i in range(1, len(track.points)):
        (t0, p0), (t1, p1) = track.points[i - 1], track.points[i]
        gap = t1 - t0
        in_occlusion = any(a - 1e-9 <= t0 and t1 <= b + 1e-9 for a, b in track.occluded)
        if p0.dist(p1) > jump_threshold and gap > 0:
            out.append({"type": "possible_identity_switch" if in_occlusion else "trajectory_jump",
                        "t": t1, "distance": round(p0.dist(p1), 4),
                        "note": "jump across declared occlusion — identity association uncertain"
                                if in_occlusion else "discontinuous jump in observed positions"})
        if gap > 1.5 * _median_dt(track):
            out.append({"type": "observation_gap", "t0": t0, "t1": t1,
                        "note": "missing evidence window — reported separately from numerical uncertainty"})
    acc = track.max_acceleration()
    if acc > max_plausible_accel:
        out.append({"type": "implausible_acceleration", "value": round(acc, 3),
                    "limit": max_plausible_accel, "note": "exceeds declared plausibility limit; treat track with suspicion"})
    return out

def _median_dt(track: Track) -> float:
    dts = sorted(b[0] - a[0] for a, b in zip(track.points, track.points[1:]))
    return dts[len(dts) // 2] if dts else 0.0
