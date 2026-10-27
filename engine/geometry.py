"""2D geometry primitives. All quantities carry their unit space with them:
callers work in either pixel space or calibrated world space, never mixed."""
from __future__ import annotations
import math
from dataclasses import dataclass

def _finite(*xs: float) -> bool:
    return all(math.isfinite(x) for x in xs)

@dataclass(frozen=True)
class Vec:
    x: float
    y: float
    def __post_init__(self):
        if not _finite(self.x, self.y): raise ValueError("non-finite vector component")
    def __add__(self, o): return Vec(self.x + o.x, self.y + o.y)
    def __sub__(self, o): return Vec(self.x - o.x, self.y - o.y)
    def scale(self, k: float): return Vec(self.x * k, self.y * k)
    def dot(self, o) -> float: return self.x * o.x + self.y * o.y
    def norm(self) -> float: return math.hypot(self.x, self.y)
    def dist(self, o) -> float: return (self - o).norm()

@dataclass(frozen=True)
class ClosestApproach:
    t_star: float      # time of closest approach (s, >= 0), inf if never closing
    d_min: float       # distance at closest approach
    closing: bool

def closest_approach(pa: Vec, va: Vec, pb: Vec, vb: Vec, horizon: float = 10.0) -> ClosestApproach:
    """Constant-velocity closest point of approach over a finite horizon.
    Analytic: minimise |r + v t|^2 for relative position r, velocity v."""
    if horizon <= 0: raise ValueError("horizon must be positive")
    r, v = pa - pb, va - vb
    vv = v.dot(v)
    if vv < 1e-12:  # no relative motion
        return ClosestApproach(math.inf, r.norm(), False)
    t = -r.dot(v) / vv
    closing = t > 0
    t_c = min(max(t, 0.0), horizon)
    return ClosestApproach(t if closing else math.inf, (r + v.scale(t_c)).norm(), closing)

def time_to_collision(pa: Vec, va: Vec, pb: Vec, vb: Vec,
                      radius_a: float, radius_b: float, horizon: float = 10.0) -> float | None:
    """Earliest t in [0, horizon] where |r + v t| <= radius_a + radius_b, else None.
    Solves the quadratic exactly; returns None (never a fake number) when the
    objects are separating, stationary relative to each other, or miss."""
    if min(radius_a, radius_b) < 0: raise ValueError("radii must be non-negative")
    r, v = pa - pb, va - vb
    R = radius_a + radius_b
    c = r.dot(r) - R * R
    if c <= 0: return 0.0  # already in contact
    a, b = v.dot(v), 2 * r.dot(v)
    if a < 1e-12 or b >= 0: return None
    disc = b * b - 4 * a * c
    if disc < 0: return None
    t = (-b - math.sqrt(disc)) / (2 * a)
    return t if 0 <= t <= horizon else None
