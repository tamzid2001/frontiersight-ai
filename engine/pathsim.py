"""Path-following counterfactual simulation — the production model.

The kinematic reference engine (engine/counterfactual.py) extrapolates
straight lines. Real actors follow paths: aisles curve, vehicles turn,
robots patrol loops. This simulator therefore replays each actor's actual
sampled trajectory (curved or straight), and applies the intervention to
the agent as a speed change *along its own path*:

- Baseline: the agent's arc-length progress s(t) is taken from its observed
  track (its true, possibly varying, speed profile).
- Counterfactual: from intervention_t, the agent's speed is reduced by
  braking at the declared deceleration toward the target factor of its
  instantaneous baseline speed, integrated at fixed dt. The agent stays on
  its path — it just arrives later. Other actors replay their observed
  trajectories unchanged (documented assumption).

Distances are then measured between the counterfactual agent position and
each other actor's observed position at the same time. Deterministic;
Monte-Carlo (optional) jitters the agent's whole path by a seeded Gaussian
offset and reports d_min percentiles. Conditional prediction under these
assumptions — not a real-world guarantee."""
from __future__ import annotations
import bisect, hashlib, json, math, random
from .geometry import Vec
from .tracking import Track

DT = 0.02

class PathMotion:
    """Arc-length table over a track's points."""
    def __init__(self, track: Track, offset: Vec = Vec(0, 0)):
        self.track = track
        self.offset = offset
        self.times = [t for t, _ in track.points]
        self.pts = [p + offset for _, p in track.points]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + a.dist(b))
        self.length = self.cum[-1]
        self.t0, self.t1 = self.times[0], self.times[-1]

    def position_at_time(self, t: float) -> Vec:
        return self.track.position_at(min(max(t, self.t0), self.t1)) + self.offset

    def arc_at_time(self, t: float) -> float:
        if t <= self.t0: return 0.0
        if t >= self.t1: return self.length
        i = bisect.bisect_right(self.times, t) - 1
        i = min(i, len(self.times) - 2)
        span = self.times[i + 1] - self.times[i]
        k = 0.0 if span <= 0 else (t - self.times[i]) / span
        return self.cum[i] + (self.cum[i + 1] - self.cum[i]) * k

    def position_at_arc(self, s: float) -> Vec:
        if not self.pts: raise ValueError("empty track")
        s = min(max(s, 0.0), self.length)
        i = bisect.bisect_right(self.cum, s) - 1
        i = min(max(i, 0), len(self.pts) - 2) if len(self.pts) > 1 else 0
        if len(self.pts) == 1: return self.pts[0]
        seg = self.cum[i + 1] - self.cum[i]
        k = 0.0 if seg <= 0 else (s - self.cum[i]) / seg
        a, b = self.pts[i], self.pts[i + 1]
        return Vec(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k)

    def baseline_speed(self, t: float) -> float:
        i = min(max(bisect.bisect_right(self.times, t) - 1, 0), len(self.times) - 2)
        span = self.times[i + 1] - self.times[i]
        return 0.0 if span <= 0 else (self.cum[i + 1] - self.cum[i]) / span

def _cf_positions(agent: PathMotion, intervention_t: float, target_factor: float,
                  decel: float, t_end: float, dt: float = DT):
    """Integrate counterfactual arc progress. Returns fn(t) -> (s_cf, v_cf)."""
    samples = []
    s = agent.arc_at_time(min(intervention_t, agent.t1))
    v = agent.baseline_speed(intervention_t)
    t = intervention_t
    samples.append((t, s, v))
    while t < t_end - 1e-9:
        step = min(dt, t_end - t)
        v_base = agent.baseline_speed(t)
        target = v_base * target_factor
        if v > target:
            v = max(target, v - decel * step)
        else:
            v = min(v_base, v + decel * step)  # never exceed baseline speed
        s += v * step
        t = round(t + step, 10)
        samples.append((t, s, v))
    def at(tt: float):
        if tt <= intervention_t: return agent.arc_at_time(tt), agent.baseline_speed(tt)
        for (t0, s0, v0), (t1, s1, v1) in zip(samples, samples[1:]):
            if t0 <= tt <= t1:
                k = 0.0 if t1 == t0 else (tt - t0) / (t1 - t0)
                return s0 + (s1 - s0) * k, v0 + (v1 - v0) * k
        return samples[-1][1], samples[-1][2]
    return at

def simulate_on_paths(agent_track: Track, others: list, intervention_t: float,
                      speed_reduction_pct: float, braking_decel: float = 2.5,
                      max_decel: float = 6.0, position_sigma: float = 0.0,
                      mc_runs: int = 0, seed: int = 42, out_step: float = 0.1) -> dict:
    """others: list[Track]. Returns per-actor distance diagnostics + series."""
    for name, v in (("intervention_t", intervention_t), ("braking_decel", braking_decel)):
        if not math.isfinite(v): raise ValueError(f"{name} must be finite")
    if not 0 <= speed_reduction_pct <= 100: raise ValueError("speed reduction must be in [0,100]")
    if not 0 <= braking_decel <= max_decel: raise ValueError("braking decel must be in [0, max_decel]")
    if not others: raise ValueError("need at least one other actor")
    factor = 1.0 - speed_reduction_pct / 100.0
    agent = PathMotion(agent_track)
    t_start = max(agent.t0, min(o.points[0][0] for o in others))
    t_end = min(agent.t1, max(o.points[-1][0] for o in others))
    if t_end <= t_start: raise ValueError("tracks do not overlap in time")
    cf_at = _cf_positions(agent, intervention_t, factor, braking_decel, t_end)

    def run_pair(other: Track, agent_motion: PathMotion, cf):
        om = PathMotion(other)
        series_o, series_c = [], []
        d_o = d_c = math.inf
        n = int((t_end - t_start) / out_step)
        for i in range(n + 1):
            t = round(t_start + i * out_step, 4)
            po, pc = agent_motion.position_at_time(t), None
            s_cf, _ = cf(t)
            pc = agent_motion.position_at_arc(s_cf)
            q = om.position_at_time(t)
            do, dc = po.dist(q), pc.dist(q)
            d_o, d_c = min(d_o, do), min(d_c, dc)
            series_o.append([t, round(po.x, 4), round(po.y, 4), round(q.x, 4), round(q.y, 4), round(do, 4)])
            series_c.append([t, round(pc.x, 4), round(pc.y, 4), round(q.x, 4), round(q.y, 4), round(dc, 4)])
        R = agent_track.radius + other.radius
        return {"original": {"d_min": round(d_o, 4), "contact": d_o <= R},
                "counterfactual": {"d_min": round(d_c, 4), "contact": d_c <= R},
                "delta_d_min": round(d_c - d_o, 4), "radius_sum": R,
                "trajectories": {"original": series_o, "counterfactual": series_c}}

    results, focus, worst_key = {}, None, math.inf
    for o in others:
        r = run_pair(o, agent, cf_at)
        results[o.object_id] = r
        if r["original"]["d_min"] < worst_key: worst_key, focus = r["original"]["d_min"], o.object_id
    manifest_src = {"agent": agent_track.object_id, "agent_points": len(agent_track.points),
                    "agent_fingerprint": agent_track.object_id + ":" + str(len(agent_track.points)),
                    "others": sorted(results), "intervention_t": intervention_t,
                    "speed_reduction_pct": speed_reduction_pct, "braking_decel": braking_decel,
                    "path_model": "pathsim-v1 (arc-length speed integration along observed path)",
                    "manifest_schema": 3}
    out = {"agent_id": agent_track.object_id, "focus_other": focus, "results": results,
           "worst_original_d_min": round(min(r["original"]["d_min"] for r in results.values()), 4),
           "worst_counterfactual_d_min": round(min(r["counterfactual"]["d_min"] for r in results.values()), 4),
           "monte_carlo": None, "params": manifest_src,
           "manifest_hash": hashlib.sha256(json.dumps(manifest_src, sort_keys=True).encode()).hexdigest(),
           "assumptions": ["agent keeps its observed path; only its speed profile changes",
                           "other actors replay their observed trajectories unchanged",
                           "braking at declared decel toward the target speed factor",
                           "conditional prediction under these assumptions — not a real-world guarantee"]}
    out["delta_worst_d_min"] = round(out["worst_counterfactual_d_min"] - out["worst_original_d_min"], 4)
    if mc_runs > 0:
        if position_sigma <= 0: raise ValueError("Monte Carlo requires position_sigma > 0")
        rng = random.Random(seed)
        focus_track = next(o for o in others if o.object_id == focus)
        vals = []
        for _ in range(mc_runs):
            jitter = Vec(rng.gauss(0, position_sigma), rng.gauss(0, position_sigma))
            jm = PathMotion(agent_track, offset=jitter)
            cf_j = _cf_positions(jm, intervention_t, factor, braking_decel, t_end)
            vals.append(run_pair(focus_track, jm, cf_j)["counterfactual"]["d_min"])
        vals.sort()
        out["monte_carlo"] = {"runs": mc_runs, "seed": seed, "position_sigma": position_sigma,
                              "focus_other": focus,
                              "d_min_p05": round(vals[int(0.05 * mc_runs)], 4),
                              "d_min_p50": round(vals[int(0.50 * mc_runs)], 4),
                              "d_min_p95": round(vals[min(mc_runs - 1, int(0.95 * mc_runs))], 4),
                              "independence_assumption": "Gaussian offset of the agent's whole path; others held at observed trajectories"}
    return out
