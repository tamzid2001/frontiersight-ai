import pytest
from engine.geometry import Vec
from engine.iou_tracking import build_tracks, iou
from engine.multi import analyse_all, simulate_agent, focus_pair
from engine.kinematics import Calibration
from engine import scenarios as scen
from services.api.server import parse_tracks

def _frame(t, boxes):
    return {"t": t, "records": [{"box": b, "confidence": 0.9} for b in boxes]}

def test_iou_tracker_links_and_separates():
    frames = [_frame(0.0, [{"x1": 0, "y1": 0, "x2": 40, "y2": 40}, {"x1": 200, "y1": 0, "x2": 240, "y2": 40}]),
              _frame(0.5, [{"x1": 20, "y1": 0, "x2": 60, "y2": 40}, {"x1": 200, "y1": 20, "x2": 240, "y2": 60}]),
              _frame(1.0, [{"x1": 40, "y1": 0, "x2": 80, "y2": 40}, {"x1": 200, "y1": 40, "x2": 240, "y2": 80}])]
    tracks = build_tracks(frames, "person")
    assert len(tracks) == 2 and all(len(t.points) == 3 for t in tracks)
    assert iou({"x1": 0, "y1": 0, "x2": 10, "y2": 10}, {"x1": 0, "y1": 0, "x2": 10, "y2": 10}) == 1.0

def test_multi_object_scenarios_analyse():
    for name in ("warehouse-multi", "intersection-crossing"):
        sc = scen.build(name)
        assert len(sc["tracks"]) >= 4
        pairs = analyse_all(sc["tracks"], Calibration(sc["calibration"]["metres_per_pixel"]))
        assert len(pairs) >= 6 and focus_pair(pairs) is not None

def test_multi_counterfactual_agent_vs_world():
    sc = scen.build("warehouse-multi")
    agent = sc["tracks"][0]; t0 = agent.points[0][0]
    others = [(t.object_id, t.position_at(t0), t.velocity_at(1), t.radius) for t in sc["tracks"][1:]]
    r = simulate_agent((agent.position_at(t0), agent.velocity_at(1), agent.radius), others, 1.0, 50)
    assert set(r["per_actor"]) == {t.object_id for t in sc["tracks"][1:]}
    assert r["worst_counterfactual_d_min"] >= 0

def test_parse_tracks_validation():
    good = [{"object_id": "a", "category": "forklift", "points": [[0, 0, 0], [1, 5, 0]], "radius": 1},
            {"object_id": "b", "category": "pedestrian", "points": [[0, 9, 3], [1, 8, 3]], "radius": 0.5}]
    assert len(parse_tracks(good)) == 2
    with pytest.raises(ValueError): parse_tracks(good[:1])
    with pytest.raises(ValueError): parse_tracks([{"object_id": "x", "points": [[0, 0, 0]]}] * 2)

def test_custom_endpoints_via_http():
    import json as _json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from services.api.server import H
    srv = ThreadingHTTPServer(("127.0.0.1", 8799), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    def post(path, payload):
        req = urllib.request.Request(f"http://127.0.0.1:8799{path}", method="POST",
                                     data=_json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        return _json.loads(urllib.request.urlopen(req, timeout=10).read())
    tracks = [{"object_id": "forklift-1", "category": "forklift", "space": "pixel", "radius": 18,
               "points": [[0, 100, 300], [1, 180, 300], [2, 260, 300]]},
              {"object_id": "pedestrian-1", "category": "pedestrian", "space": "pixel", "radius": 9,
               "points": [[0, 400, 100], [1, 400, 200], [2, 400, 300]]}]
    out = post("/api/analyze-custom", {"tracks": tracks})
    assert out["run"]["findings"]["pairs"][0]["units"] == "px"  # uncalibrated stays pixel
    out2 = post("/api/analyze-custom", {"tracks": tracks, "metres_per_pixel": 0.05})
    assert out2["run"]["findings"]["pairs"][0]["metric_claims"] is True
    cf = post("/api/counterfactual-custom", {"tracks": tracks, "agent_id": "forklift-1", "speed_reduction_pct": 50})
    assert "per_actor" in cf and "pedestrian-1" in cf["per_actor"]
    tr = post("/api/tracks", {"category": "person", "frames": [
        {"t": 0, "records": [{"box": {"x1": 0, "y1": 0, "x2": 40, "y2": 40}}]},
        {"t": 1, "records": [{"box": {"x1": 25, "y1": 0, "x2": 65, "y2": 40}}]}]})
    assert len(tr["tracks"]) == 1 and len(tr["tracks"][0]["points"]) == 2
    srv.shutdown()
