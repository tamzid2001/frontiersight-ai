"""Bounded, auditable multi-agent workflow.

Roles: Scene Analyst -> Research Planner -> (deterministic analysis) ->
Counterfactual Designer -> Verification Controller -> Evidence Writer.
Model-backed roles call Muse Spark when a key is configured; otherwise they
run in clearly labelled FIXTURE_REPLAY mode. Deterministic stages always run
the real engine. Every stage records status, attribution, inputs/outputs hash,
retries, and artifact ids. No stage can touch physical equipment; external
state changes require human approval (export gate)."""
from __future__ import annotations
import hashlib, json, time, uuid
from dataclasses import dataclass, field
from engine.geometry import Vec
from engine.kinematics import Calibration, analyse_pair
from engine.pathsim import simulate_on_paths
from engine.tracking import diagnostics
from engine.uncertainty import evidence_report
from integrations.meta import spark

STAGES = ["scene_analyst", "research_planner", "segmentation", "scene_extraction",
          "hypothesis", "simulation", "independent_verification", "human_review", "export"]

def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

@dataclass
class Stage:
    name: str
    status: str = "pending"     # pending|running|completed|failed|skipped|awaiting_human
    attribution: str = ""
    detail: dict = field(default_factory=dict)
    artifact: str = ""
    retries: int = 0

@dataclass
class Run:
    run_id: str
    scenario_id: str
    mode: str                   # LIVE_META | FIXTURE_REPLAY
    stages: list = field(default_factory=list)
    findings: dict = field(default_factory=dict)
    def to_dict(self):
        return {"run_id": self.run_id, "scenario_id": self.scenario_id, "mode": self.mode,
                "stages": [{"name": s.name, "status": s.status, "attribution": s.attribution,
                            "artifact": s.artifact, "retries": s.retries, "detail": s.detail} for s in self.stages],
                "findings": self.findings}

_checkpoint_store: dict = {}

def run_analysis(scenario: dict, speed_reduction_pct: float = 40.0, intervention_t: float = 1.0,
                 human_approved: bool = False, idempotency_key: str | None = None,
                 model: str | None = None) -> Run:
    if len(scenario.get("tracks", [])) < 2:
        raise ValueError("scene needs at least two tracks to analyse interactions")
    if len({tr.space for tr in scenario["tracks"]}) > 1:
        raise ValueError("all tracks must share one coordinate space (convert pixel tracks with calibration first)")
    _cache_key = None
    if idempotency_key is not None:
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise ValueError("idempotency_key must be a string of 1..128 characters")
        _fp = hashlib.sha256(json.dumps(
            {"s": scenario.get("id"), "t": [ (tr.object_id, len(tr.points)) for tr in scenario["tracks"]],
             "sr": speed_reduction_pct, "it": intervention_t, "ha": human_approved},
            sort_keys=True).encode()).hexdigest()
        _cache_key = (idempotency_key, _fp)
        if _cache_key in _checkpoint_store:
            return _checkpoint_store[_cache_key]
    live = spark.configured()
    run = Run(str(uuid.uuid4())[:8], scenario["id"], "LIVE_META" if live else "FIXTURE_REPLAY")
    def stage(name, attribution, fn):
        s = Stage(name, "running", attribution); run.stages.append(s)
        try:
            detail, artifact_src = fn(); s.status, s.detail = "completed", detail
            s.artifact = _hash(artifact_src)
        except Exception as e:
            s.status, s.detail = "failed", {"error": str(e)[:300]}
        return s

    tracks = scenario["tracks"]
    cal = Calibration(scenario["calibration"].get("metres_per_pixel"))
    cal.validate()

    stage("scene_analyst", f"Meta:{spark.MODEL}" if live else "FIXTURE_REPLAY",
          lambda: ({"objects": [{"id": t.object_id, "category": t.category, "source": t.source} for t in tracks],
                    "segmentation_targets": sorted({t.category for t in tracks}),
                    "note": "targets proposed for SAM 3.1 segmentation; fixture tracks are pre-labelled FIXTURE"},
                   [t.object_id for t in tracks]))
    stage("research_planner", "deterministic-policy",
          lambda: ({"goal": "quantify closest approach and test a braking counterfactual",
                    "allowed_tools": ["geometry.cpa", "kinematics.ttc", "counterfactual.simulate"],
                    "denied_tools": ["physical_robot_control", "unbounded_agent_loop"]}, "policy-v1"))

    def _seg():
        if live:
            return ({"status": "available", "model": "sam-3.1",
                     "note": "use /api/meta/segment with an image data URL; fixture replay uses labelled fixture tracks"}, "sam")
        return ({"status": "unavailable_offline", "reason": "BLOCKED_CREDENTIALS",
                 "note": "fixture tracks replayed; no segmentation was performed or claimed"}, "sam-offline")
    stage("segmentation", "Meta:sam-3.1" if live else "FIXTURE_REPLAY", _seg)

    analysis = {}
    def _extract():
        from engine.multi import analyse_all
        pairs = analyse_all(tracks, cal)
        diags = {t.object_id: diagnostics(t, jump_threshold=2.0, max_plausible_accel=8.0) for t in tracks}
        ev = {t.object_id: evidence_report(t) for t in tracks}
        analysis.update({"pairs": pairs, "diagnostics": diags, "evidence": ev})
        return ({"pairs": pairs, "track_diagnostics": diags}, {"pairs": pairs, "diags": diags})
    stage("scene_extraction", "deterministic-engine", _extract)

    from engine.multi import focus_pair
    from engine.geometry import Vec as _Vec
    _fp = focus_pair(analysis.get("pairs", [])) if analysis.get("pairs") else None
    _by_id = {t.object_id: t for t in tracks}
    agent = _by_id[_fp["pair"][0]] if _fp else tracks[0]
    other = _by_id[_fp["pair"][1]] if _fp and len(tracks) > 1 else tracks[-1]
    _sim_error = None
    try:
        t0 = max(agent.points[0][0], other.points[0][0])
        pa, pb = agent.position_at(t0), other.position_at(t0)
        va = agent.velocity_at(1) if len(agent.points) > 1 else _Vec(0, 0)
        vb = other.velocity_at(1) if len(other.points) > 1 else _Vec(0, 0)
    except Exception as _e:  # disjoint/insufficient tracks: sim stage reports it, run survives
        _sim_error = f"cannot initialise simulation: {_e}"
        pa = pb = va = vb = _Vec(0, 0)

    hypothesis = {"hypothesis": f"Reduce {agent.object_id} speed by {speed_reduction_pct:.0f}% from t={intervention_t}s",
                  "intervention": {"speed_reduction_pct": speed_reduction_pct, "intervention_time_s": intervention_t},
                  "rationale": "fixture default intervention (no model call made)"}
    def _hyp():
        nonlocal hypothesis
        if live:
            try:
                obj, meta = spark.propose_hypothesis({"pairs": analysis["pairs"], "agent": agent.object_id}, model)
                hypothesis = obj
                return ({"hypothesis": obj, "model_call": meta}, obj)
            except Exception as e:
                return ({"hypothesis": hypothesis, "model_call": None,
                         "note": f"model call failed ({str(e)[:160]}); deterministic default intervention used instead"}, hypothesis)
        return ({"hypothesis": hypothesis, "model_call": None,
                 "note": "FIXTURE_REPLAY: deterministic default intervention; no model call was made"}, hypothesis)
    stage("hypothesis", f"Meta:{spark.MODEL}" if live else "FIXTURE_REPLAY", _hyp)

    iv = hypothesis["intervention"]
    sim = {}
    def _sim():
        if _sim_error: raise ValueError(_sim_error)
        full = simulate_on_paths(agent, [other], intervention_t=float(iv["intervention_time_s"]),
                                 speed_reduction_pct=float(iv["speed_reduction_pct"]),
                                 position_sigma=0.15, mc_runs=200, seed=42)
        r = full["results"][other.object_id]
        sim.update({"original": r["original"], "counterfactual": r["counterfactual"],
                    "delta_d_min": r["delta_d_min"], "monte_carlo": full.get("monte_carlo"),
                    "manifest_hash": full["manifest_hash"], "params": full["params"],
                    "assumptions": full["assumptions"], "model": "pathsim-v1"})
        return ({"original": r["original"], "counterfactual": r["counterfactual"],
                 "delta_d_min": r["delta_d_min"], "monte_carlo": full.get("monte_carlo"),
                 "manifest_hash": full["manifest_hash"], "model": "pathsim-v1 (path-following)"}, full["manifest_hash"])
    stage("simulation", "deterministic-engine", _sim)

    def _verify():
        import hashlib as _hl
        recomputed = _hl.sha256(json.dumps(sim.get("params", {}), sort_keys=True).encode()).hexdigest() \
            if sim.get("params") else ""
        checks = [{"check": "counterfactual_did_not_worsen_d_min", "passed": sim.get("delta_d_min", -1) >= 0},
                  {"check": "manifest_hash_recomputable",
                   "passed": bool(sim.get("manifest_hash")) and recomputed == sim.get("manifest_hash")},
                  {"check": "metric_claims_match_coordinate_space",
                   "passed": all((not p["metric_claims"]) or p.get("space") == "world" for p in analysis["pairs"])},
                  {"check": "model_proposed_intervention_disclosed",
                   "passed": True,
                   "note": "intervention parameters may be model-proposed (see hypothesis stage); they are inputs, never measurements"}]
        return ({"checks": checks, "verdict": "PASS" if all(c["passed"] for c in checks) else "FAIL"}, checks)
    stage("independent_verification", "deterministic-engine", _verify)

    s = Stage("human_review", "awaiting_human" if not human_approved else "completed", "human",
              {"note": "export of the evidence packet requires explicit human approval" if not human_approved
                       else "approved for export"}); run.stages.append(s)
    s2 = Stage("export", "completed" if human_approved else "skipped", "deterministic-engine",
               {"note": "evidence packet available from /api/report/" + scenario["id"] if human_approved
                        else "blocked until human review approves"}); run.stages.append(s2)

    run.findings = {"pairs": analysis["pairs"], "simulation_summary":
                    {"original": sim.get("original"), "counterfactual": sim.get("counterfactual"),
                     "delta_d_min": sim.get("delta_d_min"), "monte_carlo": sim.get("monte_carlo")},
                    "hypothesis": hypothesis,
                    "provenance": {"observations": (f"{scenario.get('kind', 'FIXTURE')} (synthetic, ground truth held separately)"
                                                    if scenario.get("kind") == "SYNTHETIC_FIXTURE"
                                                    else f"{scenario.get('kind', 'USER_UPLOADED')} (user-supplied tracks, no ground truth held)"),
                                   "track_sources": sorted({tr.source for tr in tracks}),
                                   "calculations": "DETERMINISTIC (engine/)",
                                   "model_contributions": "hypothesis/narration only" if live else "none (fixture replay)",
                                   "assumptions": sim.get("assumptions", [])}}
    if _cache_key is not None and len(_checkpoint_store) < 256:
        _checkpoint_store[_cache_key] = run
    return run
