"""MCP (Model Context Protocol) server — FrontierSight's deterministic surface.

Shared by POST /api/mcp (Streamable-HTTP style JSON-RPC) and
scripts/mcp_stdio.py (stdio bridge, same handlers, works offline).
Model-backed tools are intentionally out of scope for MCP v1: this server
exposes only deterministic, reproducible capabilities, so an agent calling
it can never spend the host's Meta API credits or fabricate a measurement.
Engine errors surface as MCP tool errors (isError) with the engine message.
"""
from __future__ import annotations
import json
from engine import scenarios as scen
from engine.curves import sample_tracks
from engine.kinematics import Calibration, analyse_pair
from engine.pathsim import simulate_on_paths
from integrations.meta.spark import validate_scene, ModelError

PROTOCOL = "2024-11-05"
SERVER = {"name": "frontiersight-ai", "version": "0.30.0"}

def _schema(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}

TOOLS = [
    {"name": "server_info", "description": "FrontierSight server identity, model, and honesty labels.",
     "inputSchema": _schema({})},
    {"name": "list_scenarios", "description": "List built-in demonstration scenarios with descriptions.",
     "inputSchema": _schema({})},
    {"name": "get_scenario", "description": "Full scenario document: tracks (timestamped observations) and separately-held ground truth (path definitions).",
     "inputSchema": _schema({"name": {"type": "string", "enum": scen.SCENARIOS}}, ["name"])},
    {"name": "analyse_scenario", "description": "Deterministic proximity analysis of a built-in scenario: per-pair measured (along-trajectory) and predicted (CPA/TTC) metrics. No LLM is involved.",
     "inputSchema": _schema({"name": {"type": "string", "enum": scen.SCENARIOS},
                             "near_miss_distance": {"type": "number", "default": 1.0}}, ["name"])},
    {"name": "analyse_tracks", "description": "Deterministic proximity analysis of user-supplied tracks. Pixel-space tracks never produce metric claims unless converted with a declared metres_per_pixel.",
     "inputSchema": _schema({"tracks": {"type": "array"}, "metres_per_pixel": {"type": ["number", "null"]}}, ["tracks"])},
    {"name": "simulate_counterfactual", "description": "Path-following braking counterfactual: the named agent slows along its own (possibly curved) path; other actors replay observed trajectories. Monte-Carlo is capped for anonymous callers.",
     "inputSchema": _schema({"scenario": {"type": "string"}, "agent_id": {"type": "string"},
                             "intervention_t": {"type": "number", "default": 1.0},
                             "speed_reduction_pct": {"type": "number", "default": 40},
                             "braking_decel": {"type": "number", "default": 2.5},
                             "mc_runs": {"type": "integer", "default": 100}}, [])},
    {"name": "sample_paths", "description": "Sample scene objects (waypoints + straight|smooth curve + speed/mode) into timestamped tracks using Catmull-Rom arc-length parameterisation.",
     "inputSchema": _schema({"objects": {"type": "array"}}, ["objects"])},
    {"name": "validate_scene", "description": "Validate a generated scene document against the Create Lab scene schema. Rejects (never repairs) invalid scenes.",
     "inputSchema": _schema({"scene": {"type": "object"}}, ["scene"])},
]

def _ok(result) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "structuredContent": result if isinstance(result, dict) else {"result": result}}

def call_tool(name: str, args: dict) -> dict:
    if name == "server_info":
        return _ok({"server": SERVER, "protocol": PROTOCOL,
                    "labels": {"deterministic_engine": True, "model_backed_tools": False,
                               "real_video_evaluation_completed": False,
                               "no_safety_certification_claimed": True}})
    if name == "list_scenarios":
        return _ok({"scenarios": [{"id": n, "description": scen.build(n)["description"]} for n in scen.SCENARIOS]})
    if name == "get_scenario":
        return _ok(scen.scenario_to_dict(scen.build(args["name"])))
    if name == "analyse_scenario":
        sc = scen.build(args["name"])
        cal = Calibration(sc["calibration"].get("metres_per_pixel"))
        pairs = [analyse_pair(a, b, cal, near_miss_distance=float(args.get("near_miss_distance", 1.0)))
                 for i, a in enumerate(sc["tracks"]) for b in sc["tracks"][i + 1:]]
        return _ok({"scenario": sc["id"], "kind": sc["kind"], "pairs": pairs})
    if name == "analyse_tracks":
        from services.api.server import parse_tracks
        from engine.kinematics import to_world
        tracks = parse_tracks(args["tracks"])
        mpp = args.get("metres_per_pixel")
        cal = Calibration(float(mpp)) if mpp is not None else Calibration(None)
        if mpp is not None: tracks = [to_world(t, cal) for t in tracks]
        pairs = [analyse_pair(a, b, cal) for i, a in enumerate(tracks) for b in tracks[i + 1:]]
        return _ok({"pairs": pairs})
    if name == "simulate_counterfactual":
        sc = scen.build(args.get("scenario", "warehouse-near-miss"))
        by_id = {t.object_id: t for t in sc["tracks"]}
        agent = by_id.get(args.get("agent_id"), sc["tracks"][0])
        others = [t for t in sc["tracks"] if t.object_id != agent.object_id]
        mc = min(int(args.get("mc_runs", 100)), 200)  # anonymous MCP cap (Explorer limit)
        out = simulate_on_paths(agent, others, float(args.get("intervention_t", 1.0)),
                                float(args.get("speed_reduction_pct", 40)),
                                braking_decel=float(args.get("braking_decel", 2.5)),
                                position_sigma=0.15, mc_runs=mc, seed=42)
        return _ok(out)
    if name == "sample_paths":
        tracks = sample_tracks(args["objects"])
        return _ok({"tracks": [scen.track_to_dict(t) for t in tracks]})
    if name == "validate_scene":
        return _ok({"valid": True, "scene": validate_scene(args["scene"])})
    raise KeyError(f"unknown tool: {name}")

def handle_jsonrpc(body: dict) -> dict | None:
    """Returns the JSON-RPC response object, or None for notifications."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": (body or {}).get("id"),
                "error": {"code": -32600, "message": "invalid request: jsonrpc 2.0 expected"}}
    method, mid, params = body.get("method"), body.get("id"), body.get("params") or {}
    if mid is None:  # notification (e.g. notifications/initialized) — acknowledge silently
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                      "serverInfo": SERVER}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                result = call_tool(params.get("name", ""), params.get("arguments") or {})
            except Exception as e:
                result = {"content": [{"type": "text", "text": f"tool error: {e}"}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": f"method not found: {method}"}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"internal error: {e}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}

def catalog() -> dict:
    return {"name": SERVER["name"], "version": SERVER["version"], "protocol": PROTOCOL,
            "transport": {"http": "POST /api/mcp (JSON-RPC 2.0)", "stdio": "python3 scripts/mcp_stdio.py"},
            "tools": [{"name": t["name"], "description": t["description"]} for t in TOOLS],
            "docs": "docs/MCP.md",
            "note": "Deterministic tools only: no Meta API credits are spent and no evidence export is possible via MCP (human approval is a UI boundary)."}
