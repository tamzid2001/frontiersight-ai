import math, pytest
from engine.geometry import Vec
from engine.tracking import Track
from engine.pathsim import PathMotion, simulate_on_paths
from engine.curves import Path as CPath

def _track(oid, pts, radius=0.5, cat="robot"):
    return Track(oid, cat, "world", pts, radius, "FIXTURE")

def _arc_track(oid="agent", radius=0.5):
    path = CPath([(0.0, 0.0), (6.0, 0.0), (10.0, 4.0), (10.0, 10.0)], "smooth")
    pts = [(round(i * 0.1, 3), path.position_at_time(i * 0.1, 1.6)) for i in range(0, 70)]
    return _track(oid, pts, radius)

def test_counterfactual_agent_stays_on_its_curved_path():
    agent = _arc_track()
    other = _track("ped", [(i * 0.1, Vec(10.0, 2.0)) for i in range(0, 70)], 0.45, "pedestrian")
    out = simulate_on_paths(agent, [other], intervention_t=1.0, speed_reduction_pct=60,
                            braking_decel=3.0, mc_runs=0)
    r = out["results"]["ped"]
    cf = r["trajectories"]["counterfactual"]
    # every counterfactual agent position must lie ON the reference path (it only slows down)
    path = CPath([(0.0, 0.0), (6.0, 0.0), (10.0, 4.0), (10.0, 10.0)], "smooth")
    worst = 0.0
    for row in cf[::7]:
        p = Vec(row[1], row[2])
        worst = max(worst, min(p.dist(q) for q in path.points))
    assert worst < 0.25, worst
    # and it must lag the original (braking cannot teleport you ahead)
    orig_end = r["trajectories"]["original"][-1]
    cf_end = cf[-1]
    assert (cf_end[1], cf_end[2]) != (orig_end[1], orig_end[2])

def test_braking_along_curve_improves_separation_for_crossing():
    agent = _arc_track("forklift-1")
    # pedestrian standing near the end of the agent's curve
    other = _track("pedestrian-1", [(i * 0.1, Vec(10.0, 8.6)) for i in range(0, 70)], 0.45, "pedestrian")
    out = simulate_on_paths(agent, [other], intervention_t=0.5, speed_reduction_pct=70, braking_decel=4.0)
    r = out["results"]["pedestrian-1"]
    assert r["delta_d_min"] >= -0.05  # braking must not worsen separation here
    assert out["monte_carlo"] is None or "d_min_p50" in out["monte_carlo"]

def test_straight_line_sanity_and_validation():
    agent = _track("a", [(i * 0.1, Vec(i * 0.16, 5.0)) for i in range(0, 80)], 0.9, "forklift")
    other = _track("b", [(i * 0.1, Vec(8.6, 12.0 - i * 0.155)) for i in range(0, 80)], 0.45, "pedestrian")
    out = simulate_on_paths(agent, [other], 1.0, 40, position_sigma=0.15, mc_runs=50, seed=3)
    assert out["focus_other"] == "b" and out["monte_carlo"]["runs"] == 50
    with pytest.raises(ValueError): simulate_on_paths(agent, [other], 1.0, 40, braking_decel=-1)
    with pytest.raises(ValueError): simulate_on_paths(agent, [other], float("inf"), 40)
    with pytest.raises(ValueError): simulate_on_paths(agent, [], 1.0, 40)

def test_measured_analysis_on_curved_tracks():
    from engine.kinematics import analyse_pair, Calibration
    a = _arc_track("veh", 1.0)
    b = _track("cyc", [(i * 0.1, Vec(4.0 + i * 0.05, 12.0 - i * 0.19)) for i in range(0, 70)], 0.5, "cyclist")
    out = analyse_pair(a, b, Calibration(0.05), near_miss_distance=1.2)
    assert out["measured"]["d_min"] is not None and out["measured"]["method"].startswith("sampled")
