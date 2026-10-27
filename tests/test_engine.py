import math, pytest
from engine.geometry import Vec, closest_approach, time_to_collision
from engine.kinematics import Calibration, analyse_pair, to_world
from engine.tracking import Track, diagnostics, smooth
from engine.counterfactual import SimParams, simulate
from engine.validation import run_all
from engine import scenarios as scen

def test_head_on_ttc_exact():
    assert time_to_collision(Vec(0, 0), Vec(1, 0), Vec(10, 0), Vec(-1, 0), 0.5, 0.5) == pytest.approx(4.5)

def test_separating_no_ttc():
    assert time_to_collision(Vec(0, 0), Vec(-1, 0), Vec(10, 0), Vec(1, 0), 0.5, 0.5) is None

def test_validation_cases_all_pass():
    cases = run_all()
    assert len(cases) >= 7 and all(c["passed"] for c in cases), cases

def test_counterfactual_deterministic_and_hash_sensitive():
    kw = dict(intervention_t=1.0, speed_reduction_pct=40, params=SimParams(duration=4, dt=0.02),
              position_sigma=0.15, mc_runs=50, seed=7)
    a = simulate(Vec(0, 0), Vec(2, 0), Vec(14, 0.4), Vec(-0.5, 0), **kw)
    b = simulate(Vec(0, 0), Vec(2, 0), Vec(14, 0.4), Vec(-0.5, 0), **kw)
    assert a["manifest_hash"] == b["manifest_hash"] and a["delta_d_min"] == b["delta_d_min"]
    c = simulate(Vec(0, 0), Vec(2, 0), Vec(14, 0.4), Vec(-0.5, 0), **{**kw, "speed_reduction_pct": 10})
    assert c["manifest_hash"] != a["manifest_hash"]

def test_speed_reduction_changes_trajectory():
    r = simulate(Vec(0, 0), Vec(2, 0), Vec(30, 0), Vec(0, 0), 0.5, 30, SimParams(duration=5, dt=0.02))
    assert r["counterfactual"]["final_agent"][0] < r["original"]["final_agent"][0]

def test_uncalibrated_stays_pixel_and_blocks_metric():
    a = Track("a", "forklift", "pixel", [(0.0, Vec(0, 0)), (1.0, Vec(10, 0)), (2.0, Vec(20, 0))], 5, "FIXTURE")
    b = Track("b", "pedestrian", "pixel", [(0.0, Vec(100, 30)), (1.0, Vec(90, 30)), (2.0, Vec(80, 30))], 5, "FIXTURE")
    out = analyse_pair(a, b, Calibration(None))
    assert out["units"] == "px" and out["metric_claims"] is False
    with pytest.raises(ValueError): to_world(a, Calibration(None))
    with pytest.raises(ValueError): Calibration(-1).validate()

def test_track_invariants():
    with pytest.raises(ValueError):
        Track("x", "crate", "world", [(1.0, Vec(0, 0)), (0.5, Vec(1, 1))])
    with pytest.raises(ValueError):
        Track("x", "crate", "world", [(0.0, Vec(float("nan"), 0))])

def test_occlusion_gap_is_missing_evidence():
    sc = scen.build("occlusion-uncertainty")
    ped = [t for t in sc["tracks"] if t.object_id == "pedestrian-1"][0]
    assert ped.occluded == [(3.0, 4.5)]
    assert all(not (3.0 < t < 4.5) for t, _ in ped.points)
    diags = diagnostics(ped, jump_threshold=2.0, max_plausible_accel=8.0)
    assert any(d["type"] == "observation_gap" for d in diags)

def test_scenarios_ground_truth_separate():
    for name in scen.SCENARIOS:
        sc = scen.build(name)
        d = scen.scenario_to_dict(sc)
        assert d["kind"] == "SYNTHETIC_FIXTURE" and "ground_truth" in d and len(d["tracks"]) >= 2

def test_near_miss_scenario_detected_safe_passing_not():
    from engine.kinematics import analyse_pair as ap
    for name, expect_event in [("warehouse-near-miss", True), ("safe-passing", False)]:
        sc = scen.build(name); cal = Calibration(sc["calibration"]["metres_per_pixel"])
        out = ap(sc["tracks"][0], sc["tracks"][1], cal, near_miss_distance=1.2)
        assert (out["event"] is not None) == expect_event, (name, out)

def test_original_evidence_not_mutated_by_simulation():
    sc = scen.build("warehouse-near-miss")
    before = scen.track_to_dict(sc["tracks"][0])
    simulate(Vec(0, 0), Vec(1, 0), Vec(9, 0), Vec(-1, 0), 1.0, 50)
    assert scen.track_to_dict(sc["tracks"][0]) == before
