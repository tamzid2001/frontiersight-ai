# Architecture

The existing planar workbench remains available. An additive v2 path implements
actual ENU 3D kinematic prediction and articulated components.

```text
Browser Create Lab / Studio / Counterfactual (v1) -> existing planar engine
Browser Physical Intelligence (v2) / REST / MCP -> services.api.physical
    -> world3d schema -> spatial algebra -> typed dynamics/waypoints
    -> geometric contact + conservative swept checks -> evidence + rendering

Local video upload -> durable SQLite/files -> killable decode/SAM worker
    -> actual PTS + SAM response IDs -> pixel-space motion estimates
    -> explicit depth/calibration OR declared scale/height assumptions
    -> canonical v2 scene -> same deterministic simulator

Local USB/RTSP/file process -> bounded latest-frame queue -> sampled inference
    -> provisional tracking -> state + latency/freshness -> local HTTP/MCP
    -> observation-only ROS bridge; NO actuator surface
```

`engine/` never invokes a model or hardware driver. UI meshes/paths/charts consume
backend simulation samples. `integrations/meta/physics_edit.py` produces a typed
proposal but cannot apply it; the client requires approval and a matching scene
revision. Workspace saving, keys, profiles and model receipts are authenticated
and namespaced separately from Quantura in the existing Firestore project.

Clerk identity, Stripe entitlements, durable storage and camera operator tokens
have separate authority. A Clerk key is not a Firestore credential. No API/MCP
input can supply an org role, bypass safety validation, mint a robot permission
or override a physical interlock. The edge service is a single local operator,
not a multitenant hosted camera service.

Full contracts, numerical limitations, layer ownership/failure behavior and setup:
[Physical Intelligence](docs/physical-intelligence/README.md),
[edge/ROS](docs/physical-intelligence/EDGE.md),
[workbench API](docs/WORKBENCH_API.md), [security](SECURITY.md).
