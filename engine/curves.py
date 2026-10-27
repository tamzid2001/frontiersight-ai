"""Curved paths: Catmull-Rom splines with arc-length parameterisation.

A spline parameterised by its own t does NOT move at constant speed (it
speeds up on long segments, slows on short ones). For physical scenes that
would corrupt every velocity, CPA and TTC downstream. So the curve is
densely sampled, cumulative chord lengths are tabulated, and position is
looked up by *distance travelled* — speed along the path is then constant
to within the sampling resolution (24 samples/segment, verified by tests).

Open curves duplicate their endpoints (standard Catmull-Rom end handling);
closed curves wrap. Control points are interpolated exactly at segment
joins: the path passes through every waypoint the user placed."""
from __future__ import annotations
import bisect, math
from .geometry import Vec
from .tracking import Track

SAMPLES_PER_SEGMENT = 24

def _cr(p0, p1, p2, p3, t: float) -> Vec:
    t2, t3 = t * t, t * t * t
    return Vec(
        0.5 * ((2 * p1.x) + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
        0.5 * ((2 * p1.y) + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3))

def catmull_rom_sample(points: list, closed: bool = False,
                       samples_per_segment: int = SAMPLES_PER_SEGMENT) -> list:
    """Dense polyline approximating the spline through `points` (Vec list)."""
    if len(points) < 2: return list(points)
    if len(points) == 2 or samples_per_segment < 1:
        return _polyline_sample(points, closed, samples_per_segment)
    pts = points
    if closed:
        ext = [pts[-1]] + list(pts) + [pts[0], pts[1]]
        segments = range(1, len(ext) - 2)
    else:
        ext = [pts[0]] + list(pts) + [pts[-1]]
        segments = range(1, len(ext) - 2)
    out = []
    for i in segments:
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(samples_per_segment):
            out.append(_cr(p0, p1, p2, p3, k / samples_per_segment))
    out.append(pts[0] if closed else pts[-1])
    return out

def _polyline_sample(points: list, closed: bool, per: int) -> list:
    seq = list(points) + ([points[0]] if closed else [])
    if per <= 1: return seq
    out = []
    for a, b in zip(seq, seq[1:]):
        for k in range(per):
            t = k / per
            out.append(Vec(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t))
    out.append(seq[-1])
    return out

class Path:
    """A resolved path (straight or curved) with arc-length lookup."""
    def __init__(self, waypoints: list, curve: str = "straight", closed: bool = False):
        if curve not in ("straight", "smooth"): raise ValueError(f"unknown curve type: {curve}")
        raw = [Vec(float(x), float(y)) for x, y in waypoints]
        if not raw: raise ValueError("path needs at least one waypoint")
        self.waypoints, self.curve, self.closed = raw, curve, closed
        self.points = (catmull_rom_sample(raw, closed) if curve == "smooth"
                       else _polyline_sample(raw, closed, SAMPLES_PER_SEGMENT))
        self._cum = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self._cum.append(self._cum[-1] + a.dist(b))
        self.length = self._cum[-1]

    def position_at_distance(self, d: float) -> Vec:
        if len(self.points) == 1 or self.length == 0: return self.points[0]
        d = min(max(d, 0.0), self.length)
        i = bisect.bisect_right(self._cum, d) - 1
        i = min(i, len(self.points) - 2)
        seg = self._cum[i + 1] - self._cum[i]
        k = 0.0 if seg <= 0 else (d - self._cum[i]) / seg
        a, b = self.points[i], self.points[i + 1]
        return Vec(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k)

    def position_at_time(self, t: float, speed: float, delay: float = 0.0, mode: str = "stop") -> Vec:
        lt = max(0.0, t - delay)
        if speed <= 0 or self.length == 0: return self.points[0]
        dur = self.length / speed
        if lt >= dur:
            if mode == "loop": lt = lt % dur if dur else 0.0
            elif mode == "pingpong":
                m = lt % (2 * dur) if dur else 0.0
                lt = 2 * dur - m if m > dur else m
            else: lt = dur
        return self.position_at_distance(speed * lt)

def sample_tracks(objects: list, dt: float = 0.1, max_duration: float = 20.0) -> list:
    """Sample scene objects ({object_id, category, waypoints, speed, radius,
    delay, curve, mode}) into Tracks at dt — the server-side source of truth
    that the Create Lab uses, so browser preview and analysis never diverge."""
    built = []
    durations = []
    for o in objects:
        closed = o.get("mode") == "loop"
        path = Path(o["waypoints"], o.get("curve", "straight"), closed)
        speed = float(o.get("speed", 0))
        dur = float(o.get("delay", 0)) + (path.length / speed if speed > 0 else 0.0)
        durations.append(dur)
        built.append((o, path))
    total = min(max_duration, max([4.0] + durations))
    tracks, t = [], 0.0
    for o, path in built:
        pts, tt = [], 0.0
        while tt <= total + 1e-9:
            pts.append((round(tt, 3), path.position_at_time(tt, float(o.get("speed", 0)),
                                                            float(o.get("delay", 0)), o.get("mode", "stop"))))
            tt = round(tt + dt, 10)
        tracks.append(Track(str(o.get("object_id", "object")), str(o.get("category", "object")),
                            "world", pts, float(o.get("radius", 0.5)), "USER_CREATED"))
    return tracks
