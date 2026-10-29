"""MCP (Model Context Protocol) server — analysis and authenticated workbench.

Shared by POST /api/mcp (Streamable-HTTP style JSON-RPC) and
scripts/mcp_stdio.py (stdio bridge, same handlers, works offline).
Model-backed/private tools require the HTTP adapter's verified workspace context.
The offline stdio bridge cannot spend credits or access private storage.
"""
from __future__ import annotations
import json
from pathlib import Path
from copy import deepcopy
from engine import scenarios as scen
from engine.curves import sample_tracks
from engine.scene_edit import resize_scene, reposition_scene, prepare_scene, simulate_scene
from engine.kinematics import Calibration, analyse_pair
from engine.pathsim import simulate_on_paths
from integrations.meta.spark import validate_scene, ModelError

PROTOCOL = "2025-11-25"
SUPPORTED_PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18", PROTOCOL)
SERVER = {"name": "frontiersight-ai", "version": "0.38.0"}

def _scene_schema():
    schema = _editor_schema("PrepareRequest")
    definitions = schema["$defs"]
    def expand(value):
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(definitions[value["$ref"].rsplit("/", 1)[1]])
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list): return [expand(item) for item in value]
        return value
    return expand(schema["properties"]["scene"])

def _schema(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}

def _editor_schema(name):
    # The served OpenAPI document is the single published contract. Rewrite its
    # references into a self-contained JSON Schema for MCP clients.
    spec = json.loads((Path(__file__).resolve().parents[2]/"apps/web/openapi.json").read_text())
    definitions = spec["components"]["schemas"]
    schema = deepcopy(definitions[name])
    selected = {}
    def visit(value):
        if isinstance(value, dict):
            ref = value.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                key = ref.rsplit("/",1)[1]
                if key not in selected:
                    selected[key] = deepcopy(definitions[key]);visit(selected[key])
            for item in value.values():visit(item)
        elif isinstance(value, list):
            for item in value:visit(item)
    visit(schema)
    schema["$defs"] = selected
    return json.loads(json.dumps(schema).replace("#/components/schemas/", "#/$defs/"))

TOOLS = [
    {"name": "resize_scene", "description": "Resize a metre-space floor and scale all object paths to fit, including sampled smooth-curve envelopes. Preserves physical sizes and speeds. Returns a new scene; never saves it.",
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
     "inputSchema": _editor_schema("ResizeRequest")},
    {"name": "reposition_scene", "description": "Move one object's first waypoint toward x/y in metres, translating its whole path without changing its shape. Clamps the translation to keep the path and radius inside the floor. Returns a new scene, not a saved mutation.",
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
     "inputSchema": _editor_schema("RepositionRequest")},
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
                             "mc_runs": {"type": "integer", "minimum": 0, "maximum": 200, "default": 100},
                             "scene": _scene_schema(),
                             "target_id": {"type": ["string", "null"]}}, [])},
    {"name": "sample_paths", "description": "Sample scene objects into timestamped tracks. Pass scene with stage_metres and objects to preserve the full floor, definitions and digest for Studio/Counterfactual playback; legacy objects-only calls return tracks.",
     "inputSchema": _schema({"objects": {"type": "array"}, "scene": _scene_schema()})},
    {"name": "validate_scene", "description": "Validate a generated scene document against the Create Lab scene schema. Rejects (never repairs) invalid scenes.",
     "inputSchema": _schema({"scene": {"type": "object"}}, ["scene"])},
]

from services.api.workbench_contract import schemas as workbench_schemas, DESCRIPTIONS
WORKBENCH_SCHEMAS = workbench_schemas(_scene_schema())
for _name, _input in WORKBENCH_SCHEMAS.items():
    _schema_with_key = deepcopy(_input)
    if _name.startswith(("create_", "update_", "delete_", "generate_", "segment_")) or _name == "describe_paths":
        _schema_with_key['properties']['idempotency_key'] = {'type':'string','pattern':'^[A-Za-z0-9_-]{16,128}$'}
        _schema_with_key['required'].append('idempotency_key')
    TOOLS.append({'name': _name, 'description': DESCRIPTIONS[_name], 'inputSchema': _schema_with_key,
                  'annotations': {'readOnlyHint': _name.startswith(('list_', 'get_', 'validate_', 'plan_', 'predict_', 'prepare_')),
                     'destructiveHint': _name.startswith(('delete_', 'update_')), 'openWorldHint': _name.startswith(('generate_', 'segment_')) or _name == 'describe_paths'}})

def _ok(result) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "structuredContent": result if isinstance(result, dict) else {"result": result}}

def call_tool(name: str, args: dict) -> dict:
    if name == "resize_scene":
        return _ok(resize_scene(args.get("scene"),args.get("width"),args.get("height")))
    if name == "reposition_scene":
        return _ok(reposition_scene(args.get("scene"),args.get("object_id"),args.get("x"),args.get("y")))
    if name == "server_info":
        return _ok({"server": SERVER, "protocol": PROTOCOL,
                    "labels": {"deterministic_engine": True, "model_backed_tools": True, "model_tools_require_authenticated_paid_workspace": True,
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
        if "scene" in args:
            if "scenario" in args: raise ValueError("supply scene or scenario, not both")
            return _ok(simulate_scene(args["scene"], args.get("agent_id"), args.get("target_id"),
                                      args.get("intervention_t", 1.0), args.get("speed_reduction_pct", 40),
                                      args.get("braking_decel", 2.5), min(int(args.get("mc_runs",100)),200)))
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
        if "scene" in args:
            if "objects" in args: raise ValueError("supply scene or objects, not both")
            return _ok(prepare_scene(args["scene"]))
        tracks = sample_tracks(args["objects"])
        return _ok({"tracks": [scen.track_to_dict(t) for t in tracks]})
    if name == "validate_scene":
        return _ok({"valid": True, "scene": validate_scene(args["scene"])})
    raise KeyError(f"unknown tool: {name}")

def handle_jsonrpc(body: dict, workbench=None) -> dict | None:
    """Returns the JSON-RPC response object, or None for notifications."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": body.get("id") if isinstance(body, dict) else None,
                "error": {"code": -32600, "message": "invalid request: jsonrpc 2.0 expected"}}
    method, mid, params = body.get("method"), body.get("id"), body.get("params", {})
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32602, "message": "params must be an object"}}
    if mid is None:  # notification (e.g. notifications/initialized) — acknowledge silently
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion") if params.get("protocolVersion") in SUPPORTED_PROTOCOLS else PROTOCOL, "capabilities": {"tools": {}},
                      "serverInfo": SERVER}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                name, args = params.get("name", ""), params.get("arguments", {})
                if not isinstance(args, dict): raise ValueError("arguments must be an object")
                if name in WORKBENCH_SCHEMAS:
                    from services.api.workbench import Workbench
                    from services.api.clerk_auth import WorkspaceError
                    if workbench is None:
                        raise WorkspaceError(401, "Authenticated HTTP is required for workbench tools. Offline stdio exposes analysis only.")
                    service = workbench() if callable(workbench) else workbench
                    args = dict(args);key = args.pop('idempotency_key', '')
                    result = _ok(service.execute(name, args, key))
                else:
                    result = call_tool(name, args)
            except Exception as e:
                result = {"content": [{"type": "text", "text": str(e) if isinstance(e, (ValueError, KeyError)) else "Tool service unavailable; no automatic retry was made."}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": f"method not found: {method}"}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": "Internal protocol error"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}

def catalog() -> dict:
    return {"name": SERVER["name"], "version": SERVER["version"], "protocol": PROTOCOL,
            "transport": {"http": "POST /api/mcp (JSON-RPC 2.0)", "stdio": "python3 scripts/mcp_stdio.py"},
            "tools": [{"name": t["name"], "description": t["description"]} for t in TOOLS],
            "docs": "docs/MCP.md",
            "note": "Analysis tools work offline. Workbench storage/model tools require authenticated HTTP; model calls require Researcher, durable idempotency and explicit invocation. No robot actuation or approval bypass."}
