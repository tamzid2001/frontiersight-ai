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

# Declared motion assumptions per category (documented, adjustable):
# accel/decel limit (m/s^2), lateral acceleration limit in curves (m/s^2),
# and minimum physically plausible turn radius (m).
DYNAMICS = {
    "forklift":   {"accel": 0.7, "lateral": 0.6, "min_turn_radius": 1.3},
    "vehicle":    {"accel": 1.6, "lateral": 1.1, "min_turn_radius": 3.2},
    "cyclist":    {"accel": 1.2, "lateral": 1.4, "min_turn_radius": 1.2},
    "pedestrian": {"accel": 1.3, "lateral": 1.6, "min_turn_radius": 0.25},
    "robot":      {"accel": 1.0, "lateral": 1.0, "min_turn_radius": 0.5},
    "shelf":      {"accel": 0.0, "lateral": 0.0, "min_turn_radius": 0.0},
    "object":     {"accel": 1.0, "lateral": 1.0, "min_turn_radius": 0.8},
}

def dynamics_for(category: str) -> dict:
    return DYNAMICS.get(category, DYNAMICS["object"])

def path_curvatures(points: list) -> list:
    """Curvature (1/m) per dense sample via circumradius of consecutive triples."""
    out = [0.0] * len(points)
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1], points[i], points[i + 1]
        ab, bc, ca = a.dist(b), b.dist(c), c.dist(a)
        area2 = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x))
        if ab * bc * ca < 1e-12 or area2 < 1e-12: continue
        r = (ab * bc * ca) / (2 * area2)
        out[i] = 1.0 / r if r > 0 else 0.0
    if len(out) > 2: out[0], out[-1] = out[1], out[-2]
    return out

def _cr(p0, p1, p2, p3, t: float) -> Vec:
    """Centripetal Catmull-Rom (Barry-Goldman, alpha=0.5) at t in [0,1] on p1->p2.
    Unlike the uniform form it cannot create cusps or self-intersecting loops
    and overshoots far less at sharp corners — the realistic default."""
    def knot(pa, pb, t0):
        d = math.hypot(pb.x - pa.x, pb.y - pa.y)
        return t0 + max(d, 1e-4) ** 0.5
    t0, t1 = 0.0, 0.0
    t1 = knot(p0, p1, t0); t2 = knot(p1, p2, t1); t3 = knot(p2, p3, t2)
    tt = t1 + t * (t2 - t1)
    def lerp(pa, pb, ta, tb, x):
        k = 0.0 if tb == ta else (x - ta) / (tb - ta)
        return Vec(pa.x + (pb.x - pa.x) * k, pa.y + (pb.y - pa.y) * k)
    a1 = lerp(p0, p1, t0, t1, tt); a2 = lerp(p1, p2, t1, t2, tt); a3 = lerp(p2, p3, t2, t3, tt)
    b1 = lerp(a1, a2, t0, t2, tt); b2 = lerp(a2, a3, t1, t3, tt)
    return lerp(b1, b2, t1, t2, tt)

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

    def min_turn_radius(self) -> float:
        ks = path_curvatures(self.points)
        kmax = max(ks) if ks else 0.0
        return (1.0 / kmax) if kmax > 1e-9 else math.inf

    def realism(self, category: str, stage: tuple = (16.0, 14.0)) -> dict:
        """Physical-plausibility report for this path under a category's limits."""
        dyn = dynamics_for(category)
        r_min = self.min_turn_radius()
        warnings = []
        if dyn["min_turn_radius"] and r_min < dyn["min_turn_radius"]:
            warnings.append(f"tightest turn radius {r_min:.2f} m is below the {category} limit "
                            f"{dyn['min_turn_radius']} m — widen the curve or add waypoints")
        if any(not (-0.05 <= q.x <= stage[0] + 0.05 and -0.05 <= q.y <= stage[1] + 0.05) for q in self.points):
            warnings.append("path leaves the stage bounds")
        return {"min_turn_radius": None if math.isinf(r_min) else round(r_min, 3),
                "turn_limit": dyn["min_turn_radius"], "warnings": warnings}

    def motion(self, cruise: float, category: str = "object", mode: str = "stop"):
        key = (cruise, category, mode)
        if getattr(self, "_motion_key", None) != key:
            self._motion_key, self._motion = key, MotionProfile(self, cruise, category, mode)
        return self._motion

    def position_at_time(self, t: float, speed: float, delay: float = 0.0, mode: str = "stop",
                         category: str = "object") -> Vec:
        lt = max(0.0, t - delay)
        if speed <= 0 or self.length == 0: return self.points[0]
        return self.motion(speed, category, mode).position_at_time(lt)

class MotionProfile:
    """Physically-plausible speed along a path: starts from rest (except loop
    mode, which is already circulating), accelerates at the category limit,
    slows for curvature (lateral-acceleration limit), and brakes to a stop at
    the end in stop mode. Built by forward/backward passes over arc length."""
    def __init__(self, path: Path, cruise: float, category: str, mode: str):
        self.path, self.mode = path, mode
        dyn = dynamics_for(category)
        a = max(dyn["accel"], 1e-3)
        pts, cum = path.points, path._cum
        n = len(pts)
        ks = path_curvatures(pts)
        v = [min(cruise, math.sqrt(dyn["lateral"] / k)) if k > 1e-6 else cruise for k in ks]
        self.cruise = cruise
        if n < 2 or path.length == 0:
            self.times, self.total_time = [0.0], 0.0; return
        if mode == "loop":
            for _ in range(2):  # circulate passes (wrap-around smoothing)
                for i in range(n):
                    j = (i + 1) % n
                    ds = (cum[j] - cum[i]) if j > i else (path.length - cum[i] + cum[j])
                    if ds > 0: v[j] = min(v[j], math.sqrt(v[i] ** 2 + 2 * a * ds))
                for i in range(n - 1, -1, -1):
                    j = (i + 1) % n
                    ds = (cum[j] - cum[i]) if j > i else (path.length - cum[i] + cum[j])
                    if ds > 0: v[i] = min(v[i], math.sqrt(v[j] ** 2 + 2 * a * ds))
        else:
            v[0] = 0.0
            if mode in ("stop", "pingpong"): v[-1] = 0.0
            for i in range(n - 2, -1, -1):
                ds = cum[i + 1] - cum[i]
                if ds > 0: v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * a * ds))
            for i in range(n - 1):
                ds = cum[i + 1] - cum[i]
                if ds > 0: v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2 * a * ds))
        self.speeds = v
        times = [0.0]
        for i in range(n - 1):
            ds = cum[i + 1] - cum[i]
            avg = (v[i] + v[i + 1]) / 2
            times.append(times[-1] + (ds / avg if avg > 1e-6 else 0.0))
        self.times = times
        self.total_time = times[-1] if times[-1] > 0 else (path.length / cruise if cruise else 0.0)

    def position_at_time(self, lt: float) -> Vec:
        path = self.path
        if not self.times or self.total_time <= 0: return path.points[0]
        if self.mode == "loop":
            lt = lt % self.total_time if self.total_time else 0.0
        elif self.mode == "pingpong":
            T = self.total_time
            m = lt % (2 * T) if T else 0.0
            lt = 2 * T - m if m > T else m
        else:
            lt = min(lt, self.total_time)
        # invert time -> arc length by interpolation over (times, cum)
        import bisect as _b
        i = min(max(_b.bisect_right(self.times, lt) - 1, 0), len(self.times) - 2)
        span = self.times[i + 1] - self.times[i]
        k = 0.0 if span <= 0 else (lt - self.times[i]) / span
        s = path._cum[i] + (path._cum[i + 1] - path._cum[i]) * k
        return path.position_at_distance(s)

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
        prof = path.motion(speed, str(o.get("category", "object")), o.get("mode", "stop")) if speed > 0 else None
        dur = float(o.get("delay", 0)) + (prof.total_time if prof else 0.0)
        durations.append(dur)
        built.append((o, path))
    total = min(max_duration, max([4.0] + durations))
    tracks, t = [], 0.0
    for o, path in built:
        pts, tt = [], 0.0
        while tt <= total + 1e-9:
            pts.append((round(tt, 3), path.position_at_time(tt, float(o.get("speed", 0)),
                                                            float(o.get("delay", 0)), o.get("mode", "stop"),
                                                            str(o.get("category", "object")))))
            tt = round(tt + dt, 10)
        tracks.append(Track(str(o.get("object_id", "object")), str(o.get("category", "object")),
                            "world", pts, float(o.get("radius", 0.5)), "USER_CREATED"))
    return tracks
