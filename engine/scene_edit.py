"""Deterministic, non-persisting Create Lab edits in declared metre space.

Coordinates and sampled curve envelopes use the browser editor's algorithms.
Neither operation changes physical radius, speed, delay or object identity.
"""
from __future__ import annotations

from copy import deepcopy
import math
from .curves import Path


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    try:
        value=float(value)
    except OverflowError:
        raise ValueError(f"{label} must be finite") from None
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def stage_size(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("stage_metres must contain width and height")
    result = [_number(v, "stage dimension") for v in value]
    if not all(6 <= v <= 60 for v in result):
        raise ValueError("stage dimensions must be between 6 and 60 metres")
    return result


def _limits(stage, radius):
    if radius < 0 or any(size < 2 * radius for size in stage):
        raise ValueError("component is too large for the floor")
    return [(radius, stage[0] - radius), (radius, stage[1] - radius)]


def _bounds(rows):
    return ([min(p[a] for p in rows) for a in range(2)],
            [max(p[a] for p in rows) for a in range(2)])


def _clamp(v, low, high):
    return max(low, min(high, v))


def fit_path(rows, stage, radius=0, envelope=None):
    """Uniformly fit a path and its sampled curve, leaving object sizes intact."""
    ranges = _limits(stage, radius)
    if not rows:
        return []
    low, high = _bounds(rows + (envelope if envelope is not None else rows))
    scale = min([1.] + [(ranges[a][1]-ranges[a][0])/(high[a]-low[a])
                        for a in range(2) if high[a] != low[a]])
    offsets = [_clamp(0, ranges[a][0]-low[a],
                      ranges[a][1]-(low[a]+(high[a]-low[a])*scale)) for a in range(2)]
    return [[low[a]+(p[a]-low[a])*scale+offsets[a] for a in range(2)] for p in rows]


def translate_path(rows, dx, dy, stage, radius=0, envelope=None):
    ranges = _limits(stage, radius)
    desired = [_number(dx, "dx"), _number(dy, "dy")]
    if not rows:
        return {"points":[],"dx":0.,"dy":0.,"clamped":False}
    low, high = _bounds(rows + (envelope if envelope is not None else rows))
    delta = []
    for axis, value in enumerate(desired):
        left, right = ranges[axis][0]-low[axis], ranges[axis][1]-high[axis]
        if left > right + 1e-8:
            raise ValueError("path does not fit the floor; resize or edit its waypoints first")
        delta.append(_clamp(value, left, max(left, right)))
    return {"points": [[p[a]+delta[a] for a in range(2)] for p in rows],
            "dx": delta[0], "dy": delta[1],
            "clamped": any(abs(delta[a]-desired[a]) > 1e-8 for a in range(2))}


def validate_document(scene):
    if not isinstance(scene, dict):
        raise ValueError("scene must be an object")
    stage = stage_size(scene.get("stage_metres"))
    objects = scene.get("objects")
    if not isinstance(objects, list) or not 0 <= len(objects) <= 24:
        raise ValueError("scene must contain 0..24 objects")
    seen = set()
    result = deepcopy(scene)
    for obj in result["objects"]:
        if not isinstance(obj, dict):
            raise ValueError("each object must be an object")
        identity = obj.get("id", obj.get("object_id"))
        if not isinstance(identity, str) or not 1 <= len(identity) <= 100 or identity in seen:
            raise ValueError("objects need unique nonempty id or object_id values, at most 100 characters")
        if "id" in obj and "object_id" in obj and obj["id"] != obj["object_id"]:
            raise ValueError("id and object_id must agree")
        seen.add(identity)
        rows = obj.get("waypoints")
        if not isinstance(rows, list) or not 0 <= len(rows) <= 24:
            raise ValueError("each path needs 0..24 waypoints")
        clean = []
        for p in rows:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise ValueError("waypoints must be X/Y pairs")
            point = [_number(v, "coordinate") for v in p]
            if any(abs(v) > 10000 for v in point):
                raise ValueError("path coordinates exceed the edit budget")
            clean.append(point)
        obj["waypoints"] = clean
        for field, maximum in (("speed", 8), ("delay", 10)):
            if field in obj and not 0 <= _number(obj[field], field) <= maximum:
                raise ValueError(f"{field} must be between 0 and {maximum}")
        radius = _number(obj.get("radius", .5), "radius")
        _limits(stage, radius)
        if obj.get("curve", "straight") not in ("straight", "smooth") or obj.get("mode", "stop") not in ("stop", "loop", "pingpong"):
            raise ValueError("unsupported path curve or mode")
        for key in ("_res", "_prof"):
            obj.pop(key, None)
    result["stage_metres"] = stage
    return result


def _envelope(obj):
    return [] if not obj["waypoints"] else [[p.x, p.y] for p in Path(obj["waypoints"], obj.get("curve", "straight"), obj.get("mode") == "loop").points]


def resize_scene(scene, width, height):
    document = validate_document(scene)
    before, after = document["stage_metres"], stage_size([width, height])
    for obj in document["objects"]:
        radius = float(obj.get("radius", .5))
        scaled = [[p[a]*after[a]/before[a] for a in range(2)] for p in obj["waypoints"]]
        obj["waypoints"] = fit_path(scaled, after, radius)
        obj["waypoints"] = fit_path(obj["waypoints"], after, radius, _envelope(obj))
    document["stage_metres"] = after
    return {"scene": document, "operation": "resize", "source": "DETERMINISTIC", "persisted": False,
            "physical_sizes_preserved": True, "speeds_preserved": True}


def reposition_scene(scene, object_id, x, y):
    document = validate_document(scene)
    if not isinstance(object_id, str):
        raise ValueError("object_id must be a string")
    obj = next((o for o in document["objects"] if o.get("id", o.get("object_id")) == object_id), None)
    if obj is None:
        raise ValueError("object_id was not found in this scene")
    if not obj["waypoints"]:
        desired = [_number(x, "x"), _number(y, "y")]
        obj["waypoints"] = fit_path([desired], document["stage_metres"], float(obj.get("radius", .5)))
        return {"scene":document,"operation":"reposition","source":"DETERMINISTIC","persisted":False,
                "clamped":obj["waypoints"][0]!=desired,"applied_translation":[0.,0.]}
    start = obj["waypoints"][0]
    move = translate_path(obj["waypoints"], _number(x, "x")-start[0], _number(y, "y")-start[1],
                          document["stage_metres"], float(obj.get("radius", .5)), _envelope(obj))
    obj["waypoints"] = move["points"]
    return {"scene": document, "operation": "reposition", "source": "DETERMINISTIC", "persisted": False,
            "clamped": move["clamped"], "applied_translation": [move["dx"], move["dy"]]}


def scene_to_scenario(scene):
    """Build the canonical metre-space handoff; preserve definitions, not caches.

    Sampling is bounded to 20 seconds at 10 Hz by engine.curves. Appearance is
    retained separately from tracks and never used as collision geometry.
    """
    import hashlib
    import json
    from .curves import DYNAMICS, sample_tracks
    document = validate_document(scene)
    if not document['objects']:
        raise ValueError('place at least one object before preparing playback')
    definitions = []
    for obj in document['objects']:
        if not obj['waypoints']:
            raise ValueError('all objects must be placed before preparing playback')
        if obj.get('category', 'object') not in DYNAMICS:
            raise ValueError('unsupported component category')
        definitions.append(dict(obj, object_id=obj.get('id', obj.get('object_id'))))
    serialized = json.dumps({key:document[key] for key in ("stage_metres", "objects")}, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return {
        'id': str(document.get('id', 'lab-current'))[:64],
        'description': str(document.get('name', 'Current Create Lab scene'))[:200],
        'kind': 'USER_UPLOADED',
        'calibration': {'metres_per_pixel': None, 'frame': 'Create Lab stage (metres)'},
        'disclaimer': 'User-declared planar scene; appearance is illustrative, not physical calibration.',
        'stage_metres': document['stage_metres'], 'objects': document['objects'],
        'scene_digest': hashlib.sha256(serialized.encode()).hexdigest(),
        'tracks': sample_tracks(definitions), 'ground_truth': {},
    }


def prepare_scene(scene):
    """JSON-ready scene for identical Studio/Counterfactual playback."""
    from .scenarios import scenario_to_dict
    return scenario_to_dict(scene_to_scenario(scene))


def simulate_scene(scene, agent_id, target_id=None, intervention_t=1.0,
                   speed_reduction_pct=40, braking_decel=2.5, mc_runs=100):
    """A deterministic scene counterfactual with its original floor context."""
    from .pathsim import simulate_on_paths
    sc = scene_to_scenario(scene)
    tracks = sc['tracks']
    agent = next((tr for tr in tracks if tr.object_id == agent_id), None)
    if agent is None:
        raise ValueError('agent_id was not found in this scene')
    others = [tr for tr in tracks if tr.object_id != agent_id
              and (not target_id or tr.object_id == target_id)]
    if not others:
        raise ValueError('no comparison actor selected')
    result = simulate_on_paths(agent, others, _number(intervention_t, 'intervention_t'),
                               _number(speed_reduction_pct, 'speed_reduction_pct'),
                               braking_decel=_number(braking_decel, 'braking_decel'),
                               position_sigma=.15, mc_runs=mc_runs, seed=42)
    return dict(result, stage_metres=sc['stage_metres'], objects=sc['objects'],
                scene_digest=sc['scene_digest'])
