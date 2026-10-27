"""Deterministic counterfactual simulation: a braking intervention on one
moving agent vs. a constant-velocity other actor. Conditional prediction under
declared assumptions — never a proof of a real-world outcome.

Integration: semi-implicit Euler at fixed dt. Same inputs + seed => identical
outputs (Monte Carlo noise comes from a seeded RNG applied to *initial
position uncertainty only*; independence assumption documented in output)."""
from __future__ import annotations
import hashlib, json, math, random
from dataclasses import dataclass
from .geometry import Vec

@dataclass(frozen=True)
class SimParams:
    duration: float = 6.0
    dt: float = 0.05
    braking_decel: float = 2.5        # m/s^2 (or px/s^2), physical limit
    max_decel: float = 6.0            # hard plausibility ceiling

def _run(pa: Vec, va: Vec, pb: Vec, vb: Vec, intervention_t: float,
         target_speed_factor: float, params: SimParams, radius_sum: float):
    if not (0.0 <= target_speed_factor <= 1.0): raise ValueError("speed factor must be in [0,1]")
    if params.braking_decel > params.max_decel: raise ValueError("braking decel exceeds declared physical limit")
    if params.dt <= 0 or params.duration <= 0: raise ValueError("duration/dt must be positive")
    pa_c, va_c = pa, va
    speed0 = va.norm()
    traj, d_min, t_min = [], math.inf, 0.0
    steps = int(params.duration / params.dt)
    for i in range(steps + 1):
        t = i * params.dt
        pb_t = pb + vb.scale(t)
        d = pa_c.dist(pb_t)
        if d < d_min: d_min, t_min = d, t
        traj.append((round(t, 3), round(pa_c.x, 4), round(pa_c.y, 4), round(pb_t.x, 4), round(pb_t.y, 4), round(d, 4)))
        if t >= intervention_t and speed0 > 1e-9:
            cur = va_c.norm()
            target = speed0 * target_speed_factor
            if cur > target:
                new_speed = max(target, cur - params.braking_decel * params.dt)
                va_c = va_c.scale(new_speed / cur)
        pa_c = pa_c + va_c.scale(params.dt)
    return traj, d_min, t_min

def simulate(pa: Vec, va: Vec, pb: Vec, vb: Vec, intervention_t: float,
             speed_reduction_pct: float, params: SimParams = SimParams(),
             radius_a: float = 0.0, radius_b: float = 0.0,
             position_sigma: float = 0.0, mc_runs: int = 0, seed: int = 42) -> dict:
    """Original (no intervention) vs counterfactual (speed reduced by
    `speed_reduction_pct` starting at `intervention_t`). A 30% reduction
    provably changes the trajectory: the agent travels less far."""
    if not 0 <= speed_reduction_pct <= 100: raise ValueError("speed reduction must be in [0,100]")
    factor = 1.0 - speed_reduction_pct / 100.0
    R = radius_a + radius_b
    orig_traj, orig_dmin, orig_tmin = _run(pa, va, pb, vb, math.inf, 1.0, params, R)
    cf_traj, cf_dmin, cf_tmin = _run(pa, va, pb, vb, intervention_t, factor, params, R)
    manifest_src = {"pa": [pa.x, pa.y], "va": [va.x, va.y], "pb": [pb.x, pb.y], "vb": [vb.x, vb.y],
                    "intervention_t": intervention_t, "speed_reduction_pct": speed_reduction_pct,
                    "dt": params.dt, "duration": params.duration, "decel": params.braking_decel, "seed": seed}
    result = {
        "original": {"d_min": round(orig_dmin, 4), "t_at_d_min": orig_tmin, "contact": orig_dmin <= R,
                     "final_agent": orig_traj[-1][1:3]},
        "counterfactual": {"d_min": round(cf_dmin, 4), "t_at_d_min": cf_tmin, "contact": cf_dmin <= R,
                           "final_agent": cf_traj[-1][1:3]},
        "delta_d_min": round(cf_dmin - orig_dmin, 4),
        "trajectories": {"original": orig_traj, "counterfactual": cf_traj},
        "params": manifest_src,
        "manifest_hash": hashlib.sha256(json.dumps(manifest_src, sort_keys=True).encode()).hexdigest(),
        "assumptions": ["constant-velocity other actor", "agent brakes at declared decel to target speed",
                        "2D planar motion, no friction/steering dynamics",
                        "conditional prediction under these assumptions — not a real-world guarantee"],
    }
    if mc_runs > 0:
        if position_sigma <= 0: raise ValueError("Monte Carlo requires position_sigma > 0")
        rng = random.Random(seed)
        dmins = []
        for _ in range(mc_runs):
            jitter = Vec(rng.gauss(0, position_sigma), rng.gauss(0, position_sigma))
            _, d, _ = _run(pa + jitter, va, pb, vb, intervention_t, factor, params, R)
            dmins.append(d)
        dmins.sort()
        result["monte_carlo"] = {"runs": mc_runs, "seed": seed, "position_sigma": position_sigma,
                                 "d_min_p05": round(dmins[int(0.05 * mc_runs)], 4),
                                 "d_min_p50": round(dmins[int(0.50 * mc_runs)], 4),
                                 "d_min_p95": round(dmins[min(mc_runs - 1, int(0.95 * mc_runs))], 4),
                                 "independence_assumption": "Gaussian jitter on agent initial position only; velocities and other actor held fixed"}
    return result
