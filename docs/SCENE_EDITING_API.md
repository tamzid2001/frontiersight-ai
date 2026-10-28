# Scene editing in the browser, HTTP API and MCP

The same metre-space editing rules are available in Create Lab and through:

| Operation | HTTP | MCP tool |
|---|---|---|
| Resize the floor and object paths | `POST /api/scenes/resize` | `resize_scene` |
| Reposition an object and its path | `POST /api/scenes/reposition` | `reposition_scene` |

[OpenAPI 3.1 contract](https://frontiersight-ai.vercel.app/openapi.json).
MCP is available through `POST /api/mcp` and the local `scripts/mcp_stdio.py` bridge.
Both transports call the same Python implementations. Their input schemas are
self-contained projections of the served OpenAPI contract.

## Coordinates and resize behavior

A scene declares `stage_metres: [width, height]`, between 6 and 60 metres per axis.
Each object has a unique `id` (or `object_id`), `radius` and `waypoints: [[x,y], ...]`.
Origin is the bottom-left of the floor. Objects may have zero waypoints when
unplaced; a positioned path may have up to 24. Scenes support up to 24 objects.

On resize, every waypoint scales relative to the old dimensions. A final fit
keeps the object's radius and sampled smooth-curve envelope within the floor.
Any necessary fit uses uniform scaling and translation to avoid additional path
deformation. Physical radii, speed, delay, identity and supplied appearance fields
are preserved. Travel duration may change because the path length changes.
Impossible footprints are rejected atomically; no partial scene is returned.

Repositioning targets the **first waypoint** at `x,y`. The complete path moves
rigidly with the object. If an edge would leave the floor, movement is clamped to
the nearest permissible translation. Check `clamped` and `applied_translation`.
An unplaced object receives its first waypoint; its translation is reported as
zero because it had no previous position. Use waypoint editing to reshape a path
when rigid movement cannot reach a desired placement.

These are edits of user-declared geometry, not a safety certification or a proof
about unobserved physical objects. Bounds refer to the engine's sampled planar
paths and declared disk footprints, not a reconstructed 3D robot mesh.

## Resize example

Save this request as `resize.json`:

```json
{
  "scene": {
    "stage_metres": [16, 14],
    "objects": [{"id": "crate-1", "category": "object", "radius": 0.5,
                 "speed": 0, "waypoints": [[4, 4]]}]
  },
  "width": 8,
  "height": 7
}
```

```bash
curl --fail-with-body https://frontiersight-ai.vercel.app/api/scenes/resize \
  -H 'Content-Type: application/json' --data-binary @resize.json
```

The returned scene has floor `[8,7]` and crate position `[2,2]`, with radius `0.5`.
To reposition it, send the returned `scene`, `object_id: "crate-1"`, `x: 4`, `y: 3`
to `/api/scenes/reposition`.

MCP uses the same arguments under `params.arguments`:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
  "name":"resize_scene","arguments":{
    "scene":{"stage_metres":[16,14],"objects":[]},"width":8,"height":7
  }
}}
```

A successful tool response includes `structuredContent`; validation failures use
`result.isError: true`. HTTP validation failures use status 400. Existing POST
rate limits and ingestion limits apply.

## Persistence and model boundaries

Both editing operations return `source: "DETERMINISTIC"` and `persisted: false`.
They spend no model credits, mutate no account or saved scene, and require no
cloud hardware. Saving remains a separate authenticated scene-storage operation;
Firestore deployments retain their identity, organization and expected-version
checks. Server-generated path/profile caches are discarded from edited output.

The OpenAPI contract also describes the existing `/api/meta/segment` image
endpoint and its decoded mask PNG output. That operation calls Meta and uses the
deployment's configured key/quota. It is intentionally not a deterministic MCP
tool. A decoded silhouette is distinct from a bounding-box fallback, and
single-image extrusion depth is still an assumption.

## Browser controls

- **Move objects:** drag an object's body in 2D or 3D, or select it and click a
  destination. Its full path moves with it and stays inside the floor.
- **Edit paths:** drag individual points or click to append one; double-click or
  right-click a point to remove it.
- **Start X/Y:** precise numeric placement of the first waypoint.
- **Arrow keys:** while the 2D canvas is focused, move the selected object by
  0.1 m; Shift increases the increment to 1 m. Pointer cancellation restores the
  original path. Editing pauses preview motion.
- Floor dimensions travel with saved/shared/imported/exported scenes. Older
  workspaces without dimensions use the current floor and are fitted to it.

Video Studio sizes its preview to the viewport without stretching image aspect
ratios, keeps the playback controls beside the preview, bounds the event list,
and exposes segmentation through a visible button and expandable section.

## Verification

Run `python -m pytest -q` and `node --test tests/web-scenes.test.mjs`.
Tests cover bounds, smooth curves, empty scenes, invalid dimensions, impossible
footprints, input immutability, browser/Python geometry parity, actual HTTP/MCP
requests, the stdio bridge and OpenAPI/JSON Schema validation. Node LCOV covers
the pure browser geometry; Python Cobertura covers the editing engine.
Browser checks separately verify actual 2D/3D dragging, numeric and keyboard
movement, responsive layout and source-labelled scene rendering.


## Transfer the complete scene between views and agents

Use `POST /api/scenes/prepare` with `{"scene": {"stage_metres": [16,14], "objects": [...]}}`.
It returns a canonical scenario containing **the floor, original object/path definitions,
custom appearance, physical radii, timestamped tracks and a SHA-256 scene digest**.
Every object must be placed. Motion is sampled at 10 Hz for a common horizon of
4–20 seconds, using declared speeds, delays and path modes. No model is called.

MCP `sample_paths` accepts the same `scene` argument, returning the same scenario.
Its original `objects`-only form remains supported for older clients.

For counterfactuals, send `scene`, `agent_id`, optional `target_id` and intervention
parameters to `POST /api/counterfactual-custom`, or MCP `simulate_counterfactual`.
The floor and definitions travel with the results. MCP limits Monte-Carlo to 200;
HTTP retains plan budgets. A target selector filters comparison actors in both.
For model-backed analysis use `/api/analyze-custom` with `scene`; the response
retains that context. This operation can consume model credits and is excluded
from the deterministic MCP catalog.

Opening Studio or Counterfactual after editing Create Lab prepares a fresh scene,
invalidates the old run/approvals and rebuilds 3D geometry, even when object IDs and
sample counts did not change. Responses from superseded revisions are discarded.
A selected built-in example or saved workspace remains a deliberate choice until
Create Lab receives a newer edit. Object definitions stay separate from physical
tracks: illustrations never become measured 3D collision geometry.
