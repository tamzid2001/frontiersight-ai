"""Independently authored analytical reference cases. Each case has a known
closed-form outcome; the engine must reproduce it or reject the input.
These are the scientific acceptance gate for the geometry/kinematics code."""
from __future__ import annotations
import math
from .geometry import Vec, closest_approach, time_to_collision
from .counterfactual import SimParams, simulate

def run_all() -> list:
    cases = []
    def add(name, ok, detail): cases.append({"case": name, "passed": bool(ok), "detail": detail})

    # 1. Head-on approach: contact at (10 - 1) / 2 = 4.5 s
    t = time_to_collision(Vec(0, 0), Vec(1, 0), Vec(10, 0), Vec(-1, 0), 0.5, 0.5)
    add("head_on_contact", t is not None and abs(t - 4.5) < 1e-9, f"ttc={t}, expected 4.5")

    # 2. Moving apart: never collides, CPA at t=0
    c = closest_approach(Vec(0, 0), Vec(-1, 0), Vec(10, 0), Vec(1, 0))
    add("moving_apart", not c.closing and abs(c.d_min - 10) < 1e-9, f"d_min={c.d_min}")

    # 3. Stationary obstacle, agent passes at distance 3
    c = closest_approach(Vec(0, 0), Vec(1, 0), Vec(5, 3), Vec(0, 0))
    add("stationary_obstacle_pass", abs(c.d_min - 3) < 1e-9 and abs(c.t_star - 5) < 1e-9, f"d_min={c.d_min} t*={c.t_star}")

    # 4. Crossing trajectories with known CPA (perpendicular, miss by 1)
    c = closest_approach(Vec(0, 0), Vec(1, 0), Vec(5, -4), Vec(0, 1))
    add("crossing_near_tangent", abs(c.d_min - math.sqrt(0.5)) < 1e-6, f"d_min={c.d_min:.4f}, expected {math.sqrt(0.5):.4f}")

    # 5. Delayed braking: 40% speed cut must not decrease d_min and must move final position back
    r = simulate(Vec(0, 0), Vec(2, 0), Vec(14, 0.4), Vec(-0.5, 0), intervention_t=1.0,
                 speed_reduction_pct=40, params=SimParams(duration=6, dt=0.02))
    add("delayed_braking_helps", r["delta_d_min"] >= 0 and r["counterfactual"]["final_agent"][0] < r["original"]["final_agent"][0],
        f"delta_d_min={r['delta_d_min']}")

    # 6. Invalid inputs are rejected, not fabricated
    rejected = 0
    for fn in (lambda: time_to_collision(Vec(0, 0), Vec(1, 0), Vec(5, 0), Vec(0, 0), -1, 0),
               lambda: simulate(Vec(0, 0), Vec(1, 0), Vec(5, 0), Vec(0, 0), 0, 140),
               lambda: simulate(Vec(0, 0), Vec(1, 0), Vec(5, 0), Vec(0, 0), 0, 10, SimParams(braking_decel=99))):
        try: fn()
        except ValueError: rejected += 1
    add("invalid_inputs_rejected", rejected == 3, f"{rejected}/3 invalid inputs raised ValueError")

    # 7. Zero relative velocity: no TTC, CPA is current distance
    t = time_to_collision(Vec(0, 0), Vec(1, 0), Vec(0, 5), Vec(1, 0), 0.5, 0.5)
    c = closest_approach(Vec(0, 0), Vec(1, 0), Vec(0, 5), Vec(1, 0))
    add("zero_relative_velocity", t is None and abs(c.d_min - 5) < 1e-9, f"ttc={t} d_min={c.d_min}")
    return cases
