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

def test_curved_paths_arc_length_and_speed():
    from engine.curves import Path, catmull_rom_sample
    import math as _m
    # spline passes through its control points at segment joins
    pts = [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)]
    dense = catmull_rom_sample([Vec(*p) for p in pts], samples_per_segment=24)
    assert dense[0] == Vec(0, 0) and dense[24] == Vec(5, 5) and dense[-1] == Vec(10, 0)
    curved = Path(pts, "smooth"); straight = Path(pts, "straight")
    assert curved.length > straight.length  # the arc over the top is longer than chords... (chords are the straight path)
    # constant speed: equal time steps -> near-equal travel distances
    pos = [curved.position_at_time(t * 0.5, speed=2.0) for t in range(9)]
    steps = [a.dist(b) for a, b in zip(pos, pos[1:])]
    assert all(abs(s - 1.0) < 0.06 for s in steps), steps
    # closed loop returns to its start and has no seam jump
    loop = Path([(2.0, 2.0), (13.0, 2.0), (13.0, 11.0), (2.0, 11.0)], "smooth", closed=True)
    p0 = loop.position_at_time(0, speed=1.2)
    p_end = loop.position_at_time(loop.length / 1.2, speed=1.2, mode="loop")
    assert p0.dist(p_end) < 0.05
    # smoothness: heading changes gradually through the corner (no 90-degree kink)
    import math as _m2
    corner = Path([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], "smooth")
    dense = corner.points
    def _ang(a, b, c):
        v1, v2 = (b.x - a.x, b.y - a.y), (c.x - b.x, c.y - b.y)
        return abs(_m2.degrees(_m2.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
    max_turn = max(_ang(dense[i - 1], dense[i], dense[i + 1]) for i in range(1, len(dense) - 1))
    assert max_turn < 20, max_turn  # polyline corner would spike ~90 in one step
    with pytest.raises(ValueError): Path([(0.0, 0.0)], "bezier")

def test_sample_tracks_curved_scene():
    from engine.curves import sample_tracks
    tracks = sample_tracks([
        {"object_id": "robot-1", "category": "robot", "waypoints": [[2, 2], [13, 2], [13, 11], [2, 11]],
         "speed": 1.2, "radius": 0.55, "delay": 0, "curve": "smooth", "mode": "loop"},
        {"object_id": "pedestrian-1", "category": "pedestrian", "waypoints": [[15, 1], [8, 7], [15, 12]],
         "speed": 1.1, "radius": 0.45, "delay": 0, "curve": "smooth", "mode": "stop"}])
    assert len(tracks) == 2 and all(len(t.points) > 40 for t in tracks)
    assert tracks[0].points[0][1] == tracks[0].position_at(0)
