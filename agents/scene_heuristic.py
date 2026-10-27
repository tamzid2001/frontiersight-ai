"""Offline scene fallback — clearly labelled OFFLINE_HEURISTIC, never presented
as a model call. Keyword-matches the request to a hand-authored template so the
Create Lab prompt box still works without an API key."""
from __future__ import annotations

TEMPLATES = {
    "near-miss": [{"category": "forklift", "waypoints": [[1, 7], [7.5, 7], [13, 7]], "speed": 1.6, "radius": 0.9, "delay": 0, "mode": "stop"},
                  {"category": "pedestrian", "waypoints": [[8.6, 13], [8.6, 6], [8.6, 1]], "speed": 1.55, "radius": 0.45, "delay": 0, "mode": "stop"}],
    "crossing": [{"category": "vehicle", "waypoints": [[0.5, 7], [8, 7], [15, 7]], "speed": 2.4, "radius": 1.1, "delay": 0, "mode": "stop"},
                 {"category": "cyclist", "waypoints": [[9, 13.5], [9, 7], [9, 1]], "speed": 1.9, "radius": 0.5, "delay": 0.5, "mode": "stop"},
                 {"category": "pedestrian", "waypoints": [[14, 2], [8, 6.2], [3, 11]], "speed": 1.3, "radius": 0.45, "delay": 1, "mode": "stop"}],
    "robot cell": [{"category": "robot", "waypoints": [[2, 2], [13, 2], [13, 11], [2, 11], [2, 2]], "speed": 1.2, "radius": 0.55, "delay": 0, "mode": "loop"},
                   {"category": "forklift", "waypoints": [[1, 12], [14, 12]], "speed": 0.9, "radius": 0.9, "delay": 1, "mode": "pingpong"},
                   {"category": "shelf", "waypoints": [[8, 7]], "speed": 0, "radius": 1.4, "delay": 0, "mode": "stop"},
                   {"category": "pedestrian", "waypoints": [[15, 1], [10, 6], [15, 12]], "speed": 1.1, "radius": 0.45, "delay": 2, "mode": "stop"}],
}

def match(description: str) -> dict | None:
    d = description.lower()
    if any(k in d for k in ("robot cell", "cell", "loop", "patrol", "warehouse robot")): key = "robot cell"
    elif any(k in d for k in ("cross", "intersection", "cyclist", "vehicle", "road", "traffic")): key = "crossing"
    elif any(k in d for k in ("near", "forklift", "warehouse", "pedestrian", "aisle")): key = "near-miss"
    else: return None
    return {"name": f"offline-template-{key}", "explanation": f"Offline keyword match to the '{key}' template (no model call was made).",
            "objects": [dict(o, waypoints=[list(w) for w in o["waypoints"]]) for o in TEMPLATES[key]]}
