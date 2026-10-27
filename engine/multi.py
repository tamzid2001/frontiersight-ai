"""Multi-object analysis: all-pairs proximity + agent-vs-world counterfactual.

The counterfactual generalises engine.counterfactual.simulate: ONE agent
brakes; every other actor keeps constant velocity; we report the worst
(minimum) separation across all pairs involving the agent, per timestep."""
from __future__ import annotations
import math
from .counterfactual import SimParams, _run
from .geometry import Vec
from .kinematics import Calibration, analyse_pair

def analyse_all(tracks: list, cal: Calibration, horizon: float = 6.0,
                near_miss_distance: float = 1.0) -> list:
    if len(tracks) < 2: raise ValueError("need at least two tracks")
    out = []
    for i, a in enumerate(tracks):
        for b in tracks[i + 1:]:
            out.append(analyse_pair(a, b, cal, horizon, near_miss_distance))
    return out

def focus_pair(pairs: list) -> dict | None:
    """The pair a human should look at first: smallest d_min among closing pairs.
    Pairs without a computed d_min (insufficient/disjoint observations) are ignored."""
    usable = [p for p in pairs if p.get("d_min") is not None]
    if not usable: return None
    closing = [p for p in usable if p.get("closing")]
    return min(closing or usable, key=lambda p: p["d_min"])

def simulate_agent(agent_state, others: list, intervention_t: float,
                   speed_reduction_pct: float, params: SimParams = SimParams()) -> dict:
    """agent_state: (pos, vel, radius). others: [(object_id, pos, vel, radius)].
    Returns worst-pair d_min for original vs counterfactual, plus per-actor detail."""
    if not others: raise ValueError("need at least one other actor")
    pa, va, ra = agent_state
    per_actor, worst_o, worst_c = {}, math.inf, math.inf
    traj_o = traj_c = None
    by_actor = {}
    for oid, pb, vb, rb in others:
        from .counterfactual import simulate
        r = simulate(pa, va, pb, vb, intervention_t, speed_reduction_pct, params, ra, rb)
        per_actor[oid] = {"original_d_min": r["original"]["d_min"],
                          "counterfactual_d_min": r["counterfactual"]["d_min"],
                          "contact_original": r["original"]["contact"],
                          "contact_counterfactual": r["counterfactual"]["contact"]}
        by_actor[oid] = r["trajectories"]
        worst_o = min(worst_o, r["original"]["d_min"]); worst_c = min(worst_c, r["counterfactual"]["d_min"])
        if traj_o is None: traj_o, traj_c = r["trajectories"]["original"], r["trajectories"]["counterfactual"]
    return {"worst_original_d_min": round(worst_o, 4), "worst_counterfactual_d_min": round(worst_c, 4),
            "delta_worst_d_min": round(worst_c - worst_o, 4), "per_actor": per_actor,
            "trajectories_by_actor": by_actor,
            "trajectories": {"original": traj_o, "counterfactual": traj_c},
            "assumptions": ["single braking agent", "all other actors constant velocity",
                            "conditional prediction under declared assumptions — not a real-world guarantee"]}
